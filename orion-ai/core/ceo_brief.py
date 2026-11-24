"""Synthèse quotidienne des données opérationnelles locales."""
import json
import logging
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from urllib.parse import quote


class CEOBrief:
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(path, timeout=10)) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS ceo_briefs (
                    day TEXT PRIMARY KEY, body TEXT NOT NULL
                )
            """)

    def generate(self, today, wedding, sites, inbox, business, projects, import_directory, explicit_directory=False):
        cutoff = today + timedelta(days=7)
        statuses = {}
        priorities = []

        def add(source, title, detail, level, link, due=None):
            priorities.append({"source": source, "title": title, "detail": detail,
                               "level": level, "link": link, "due": due})

        def collect(name, provider):
            try:
                provider()
                statuses[name] = "ok"
            except (sqlite3.Error, OSError, ValueError):
                logging.getLogger(__name__).exception("Source du brief indisponible : %s", name)
                statuses[name] = "error"
                priorities[:] = [item for item in priorities if item["source"] != name]

        def wedding_priorities():
            for row in wedding().overview(today, 7)["dossiers"]:
                if not any(row[key] for key in ("late", "blocked", "drafts", "approved", "business_due")):
                    continue
                detail = (f"{row['late']} en retard · {row['blocked']} bloquée(s) · "
                          f"{row['drafts']} relance(s) à valider · {row['approved']} validée(s) · "
                          f"{row['business_due']} échéance(s) métier")
                add("Wedding", row["nom"], detail, 0 if row["late"] else 1,
                    "#wedding?dossier=" + row["id"])

        def site_priorities():
            for row in sites().brief_queue():
                failed = row["state"] == "failed"
                detail = {"failed": "Échec du dernier workflow", "draft": "Plan à valider",
                          "approved": "Contrôle après intervention à consigner"}[row["state"]]
                add("Site web", row["name"], detail + " · " + row["template"],
                    0 if failed else 1, "#site?dossier=" + row["site_id"])

        def inbox_priorities():
            for row in inbox().due_before(cutoff):
                due = row["due_date"]
                add("Mémoire", row["title"], "Échéance renseignée dans la mémoire",
                    0 if due < today.isoformat() else 1, "#memoire?entree=" + row["id"], due)

        metrics = None
        imports = {}
        file_sync = {}

        def business_priorities():
            nonlocal metrics, imports, file_sync
            store = business()
            if import_directory.is_dir() or (not explicit_directory and not import_directory.exists()):
                file_sync = store.sync_folder(import_directory)
            else:
                file_sync = {"Dossier local": {"state": "error", "detail": "Dossier d’import introuvable ou inaccessible."}}
            metrics, rows = store.summary(today, cutoff)
            imports = store.latest()
            captions = {"prospects": "Prospect à contacter", "appointments": "Rendez-vous prévu",
                        "tickets": "Ticket ouvert"}
            for row in rows:
                urgent = row["status"] == "urgent" or (row["kind"] == "appointments" and row["day"] == today.isoformat())
                link = "#support?ticket=" + quote(row["id"], safe="") if row["kind"] == "tickets" else "#ceo?imports=1"
                add("Données métier", row["title"], captions[row["kind"]], 0 if urgent else 1, link, row["day"])

        collect("Wedding", wedding_priorities)
        collect("Site web", site_priorities)
        collect("Mémoire", inbox_priorities)
        collect("Données métier", business_priorities)
        def project_priorities():
            for row in projects().priorities(today, cutoff):
                late = bool(row["due"] and row["due"] < today.isoformat())
                blocked = row["status"] == "blocked"
                details = []
                if blocked:
                    details.append("Projet bloqué")
                if row["due"] and row["due"] <= cutoff.isoformat():
                    details.append("Échéance du projet dépassée" if late else "Échéance du projet à venir")
                for key, caption in (("blocked_tasks", "bloquée(s)"), ("late_tasks", "en retard"),
                                     ("upcoming_tasks", "à échéance sous sept jours"),
                                     ("waiting_tasks", "en attente de prérequis")):
                    if row[key]:
                        details.append(f"{row[key]} tâche(s) {caption}")
                dates = [day for day in (row["due"], row["task_due"]) if day]
                add("Projets", row["title"], " · ".join([*details, row["owner"]]),
                    0 if blocked or late or row["blocked_tasks"] or row["late_tasks"] else 1,
                    "#projets?projet=" + row["id"], min(dates, default=None))

        collect("Projets", project_priorities)
        priorities.sort(key=lambda item: (item["level"], item["due"] or "", item["title"].casefold()))
        report = {"date": today.isoformat(), "until": cutoff.isoformat(),
                  "saved_at": datetime.now(timezone.utc).isoformat(), "sources": statuses,
                  "count": len(priorities), "urgent": sum(item["level"] == 0 for item in priorities),
                  "items": priorities[:50],
                  "business": metrics if statuses["Données métier"] == "ok" else None,
                  "imports": imports if statuses["Données métier"] == "ok" else {},
                  "file_sync": file_sync}
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("""
                INSERT INTO ceo_briefs VALUES (?, ?)
                ON CONFLICT(day) DO UPDATE SET body=excluded.body
            """, (report["date"], json.dumps(report, ensure_ascii=False)))
        return report

    def history(self, today):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            reports = [json.loads(row[0]) for row in db.execute("""
                SELECT body FROM ceo_briefs WHERE day<=? ORDER BY day DESC LIMIT 2
            """, (today.isoformat(),))]
        latest = reports[0] if reports else None
        previous = reports[1] if len(reports) > 1 else None
        return {"today": today.isoformat(), "latest": latest, "previous": previous}
