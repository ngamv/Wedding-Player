"""Données métier et relances d'un dossier Wedding."""
import json
from contextlib import closing
from datetime import datetime, timedelta, timezone
from uuid import uuid4


class WeddingDossier:
    def __init__(self, checklist):
        self.checklist = checklist
        with closing(checklist.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS wedding_records (
                    plan TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL,
                    data TEXT NOT NULL, PRIMARY KEY(plan, kind, id)
                );
                CREATE TABLE IF NOT EXISTS wedding_reminders (
                    plan TEXT NOT NULL, kind TEXT NOT NULL, target TEXT NOT NULL,
                    due TEXT NOT NULL, data TEXT NOT NULL,
                    PRIMARY KEY(plan, kind, target, due)
                );
                CREATE TABLE IF NOT EXISTS wedding_briefs (
                    day TEXT NOT NULL, horizon INTEGER NOT NULL, data TEXT NOT NULL,
                    PRIMARY KEY(day, horizon)
                );
            """)

    @staticmethod
    def records(db, plan):
        return {kind: {row['id']: json.loads(row['data']) for row in db.execute(
            'SELECT id, data FROM wedding_records WHERE plan=? AND kind=? ORDER BY rowid',
            (plan, kind)
        )} for kind in ('client', 'vendor', 'quote', 'payment', 'guest', 'day', 'summary')}

    @staticmethod
    def paid(records, quote_id):
        return sum(p['amount'] for p in records['payment'].values()
                   if p['quote'] == quote_id and p['status'] == 'paid')

    def read(self, plan):
        checklist = self.checklist.get(plan)
        with closing(self.checklist.connect()) as db:
            db.execute('BEGIN')
            rows = self.records(db, plan)
            reminders = [json.loads(row[0]) for row in db.execute(
                'SELECT data FROM wedding_reminders WHERE plan=? ORDER BY rowid DESC', (plan,)
            )]
        accepted = {key: q for key, q in rows['quote'].items() if q['status'] == 'accepted'}
        return {
            'records': rows, 'reminders': reminders,
            'committed': sum(q['amount'] for q in accepted.values()),
            'paid': sum(self.paid(rows, key) for key in accepted),
            'day_tasks': [t for t in checklist['tasks'] if t['offset'] == 0],
        }

    def save(self, plan, kind, key, data):
        with closing(self.checklist.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            self.checklist.get(plan)
            rows = self.records(db, plan)
            if kind in ('client', 'summary'):
                key = kind
            elif key and key not in rows[kind]:
                raise KeyError('Élément introuvable.')
            else:
                key = key or uuid4().hex
            if kind == 'quote':
                if data['vendor'] not in rows['vendor']:
                    raise ValueError('Choisissez un prestataire du dossier.')
                linked = [p for p in rows['payment'].values() if p['quote'] == key]
                if linked and (data['status'] != 'accepted' or data['amount'] < sum(p['amount'] for p in linked)):
                    raise ValueError('Ce devis doit couvrir les acomptes enregistrés.')
            if kind == 'payment':
                quote = rows['quote'].get(data['quote'])
                old = rows['payment'].get(key)
                if old and old['quote'] != data['quote']:
                    raise ValueError('Le devis associé à un acompte existant est fixe.')
                other = sum(p['amount'] for i, p in rows['payment'].items()
                            if i != key and p['quote'] == data['quote'])
                if not quote or quote['status'] != 'accepted' or other + data['amount'] > quote['amount']:
                    raise ValueError('L’acompte doit être couvert par un devis accepté.')
            db.execute('INSERT OR REPLACE INTO wedding_records VALUES (?, ?, ?, ?)',
                       (plan, kind, key, json.dumps(data, ensure_ascii=False)))
        return key

    def candidates(self, rows, today, days):
        cutoff = (today + timedelta(days=days)).isoformat()
        for kind, name, status in [('quote', 'confirmation du devis', 'requested'),
                                   ('payment', 'règlement de l’acompte', 'pending'),
                                   ('guest', 'réponse à l’invitation', 'pending')]:
            for key, item in rows[kind].items():
                due = item['due']
                if item['status'] != status or not due or due > cutoff:
                    continue
                if kind == 'quote':
                    contact = rows['vendor'][item['vendor']]
                elif kind == 'payment':
                    quote = rows['quote'][item['quote']]
                    contact = rows['vendor'][quote['vendor']]
                else:
                    contact = item
                yield (kind, key, due), {
                    'kind': kind, 'target': key, 'due': due,
                    'email': contact.get('email', ''),
                    'subject': f'Mariage · {name}',
                    'message': (
                        f"Bonjour {contact.get('name', '')},\n\n"
                        f"Je reviens vers vous au sujet de cette échéance de mariage "
                        f"({name}, le {due}, référence : {item['name']}). Pouvez-vous me confirmer où cela en est ?\n\nMerci."
                    )
                }

    def detect(self, plan, today, days):
        self.checklist.get(plan)
        with closing(self.checklist.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            for key, data in self.candidates(self.records(db, plan), today, days):
                db.execute("""
                    INSERT INTO wedding_reminders VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(plan, kind, target, due) DO UPDATE SET data=excluded.data
                    WHERE json_extract(wedding_reminders.data, '$.status')='draft'
                """,
                           (plan, *key, json.dumps({**data, 'status': 'draft'}, ensure_ascii=False)))

    def overview(self, today, days, prepare=False):
        dossiers = []
        closed = 0
        for plan in self.checklist.list():
            dossier = self.read(plan["id"])
            records = dossier["records"]
            stage = records["client"].get("client", {}).get("stage", "prospect")
            if stage == "closed":
                closed += 1
                continue
            if prepare:
                self.detect(plan["id"], today, days)
                dossier = self.read(plan["id"])
                records = dossier["records"]
            schedule = self.checklist.digest(plan["id"], today, days)
            pending = dict(self.candidates(records, today, days))
            reminders = {"draft": 0, "approved": 0}
            for reminder in dossier["reminders"]:
                key = (reminder["kind"], reminder["target"], reminder["due"])
                current = pending.get(key)
                status = reminder["status"]
                if (status in reminders and current
                        and all(reminder[field] == current[field] for field in ("email", "message"))):
                    reminders[status] += 1
            dossiers.append({
                **plan, "stage": stage,
                "late": len(schedule["en_retard"]),
                "upcoming": len(schedule["a_venir"]),
                "blocked": sum(task["bloquee"] for task in schedule["en_retard"] + schedule["a_venir"]),
                "business_due": len(pending),
                "drafts": reminders["draft"], "approved": reminders["approved"],
                "committed": dossier["committed"], "paid": dossier["paid"],
                "balance": dossier["committed"] - dossier["paid"],
            })
        dossiers.sort(key=lambda row: (-row["late"], -row["drafts"], row["date"], row["id"]))
        return {
            "date": today.isoformat(), "days": days, "closed": closed, "dossiers": dossiers,
            "totals": {field: sum(row[field] for row in dossiers) for field in
                       ("late", "upcoming", "blocked", "business_due", "drafts", "approved",
                        "committed", "paid", "balance")},
        }

    def save_brief(self, overview):
        summary = {**overview, "saved_at": datetime.now(timezone.utc).isoformat()}
        with closing(self.checklist.connect()) as db, db:
            db.execute("""
                INSERT INTO wedding_briefs VALUES (?, ?, ?)
                ON CONFLICT(day, horizon) DO UPDATE SET data=excluded.data
            """, (summary["date"], summary["days"], json.dumps(summary, ensure_ascii=False)))
        return summary

    def latest_brief(self, today, days):
        with closing(self.checklist.connect()) as db:
            reports = [json.loads(row[0]) for row in db.execute("""
                SELECT data FROM wedding_briefs WHERE horizon=? AND day<=?
                ORDER BY day DESC LIMIT 2
            """, (days, today.isoformat()))]
        previous = reports[1] if len(reports) > 1 else None
        return {"today": today.isoformat(), "latest": reports[0] if reports else None, "previous": previous}

    @staticmethod
    def get_reminder(db, key):
        row = db.execute("SELECT data FROM wedding_reminders WHERE plan=? AND kind=? AND target=? AND due=?",
                         key).fetchone()
        if row is None:
            raise KeyError("Relance introuvable.")
        return json.loads(row[0])

    @staticmethod
    def save_reminder(db, key, data):
        db.execute("UPDATE wedding_reminders SET data=? WHERE plan=? AND kind=? AND target=? AND due=?",
                   (json.dumps(data, ensure_ascii=False), *key))

    def check_current(self, db, key, data, today):
        current = dict(self.candidates(self.records(db, key[0]), today, 90)).get(key[1:])
        if current is None or any(data[field] != current[field] for field in ("email", "message")):
            raise ValueError("Échéance résolue ou contact modifié. Écartez cette relance.")

    def reserve_mail(self, key, today, message_id):
        with closing(self.checklist.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            data = self.get_reminder(db, key)
            if data["status"] != "approved" or not data["email"]:
                raise ValueError("La relance doit être validée et associée à un destinataire.")
            self.check_current(db, key, data, today)
            data.update(status="sending", mail_id=message_id,
                        mail_started_at=datetime.now(timezone.utc).isoformat())
            self.save_reminder(db, key, data)
        return data

    def finish_mail(self, key, message_id, outcome, detail):
        with closing(self.checklist.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            data = self.get_reminder(db, key)
            if data["status"] != "sending" or data.get("mail_id") != message_id:
                raise ValueError("Cette tentative n’est plus active.")
            data.update(status={"accepted": "sent", "rejected": "approved", "unknown": "unknown"}[outcome],
                        mail_outcome=outcome, mail_detail=detail,
                        mail_finished_at=datetime.now(timezone.utc).isoformat())
            self.save_reminder(db, key, data)
        return data

    def transition(self, plan, kind, target, due, action, today, result):
        with closing(self.checklist.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            key = (plan, kind, target, due)
            data = self.get_reminder(db, key)
            expected = 'draft' if action == 'approve' else 'approved'
            status = {'approve': 'approved', 'record': 'recorded', 'dismiss': 'dismissed'}[action]
            if action == 'dismiss':
                expected = data['status'] if data['status'] in ('draft', 'approved') else 'draft'
            if action == 'record' and data['status'] in ('sent', 'unknown'):
                expected = data['status']
            if action == 'record' and data['status'] == 'sending':
                age = datetime.now(timezone.utc) - datetime.fromisoformat(data['mail_started_at'])
                if age >= timedelta(minutes=5):
                    expected = 'sending'
            if data['status'] != expected:
                raise ValueError('Cette action ne correspond plus à l’état de la relance.')
            # Un brouillon ancien ne doit pas être validé après résolution ou modification de sa source.
            if action == 'approve':
                self.check_current(db, key, data, today)
            data.update(status=status)
            if action == 'approve':
                data['approved_at'] = today.isoformat()
            if action == 'record':
                data['result'] = result
                data['recorded_at'] = today.isoformat()
            self.save_reminder(db, key, data)
        return data
