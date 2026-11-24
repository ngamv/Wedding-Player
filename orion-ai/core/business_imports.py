"""Import atomique des données métier provenant de fichiers CSV."""
import csv
import hashlib
import io
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

KINDS = {
    "prospects": {"new", "contacted", "closed"},
    "appointments": {"scheduled", "done", "cancelled"},
    "tickets": {"open", "urgent", "closed"},
    "receipts": {"paid", "pending", "cancelled"},
}
MAX_FILE_BYTES = 2_000_000
HEADERS = {"id", "title", "date", "status", "amount_eur"}


def parse_rows(kind, content):
    sample = content.lstrip("\ufeff")
    first = sample.partition("\n")[0]
    delimiter = ";" if first.count(";") > first.count(",") else ","
    reader = csv.DictReader(io.StringIO(sample, newline=""), delimiter=delimiter, strict=True)
    required = HEADERS if kind == "receipts" else HEADERS - {"amount_eur"}
    fields = reader.fieldnames or []
    if len(set(fields)) != len(fields) or not required <= set(fields) <= HEADERS:
        raise ValueError("Colonnes attendues : " + ", ".join(sorted(required)))
    result = {}
    for row in reader:
        try:
            if None in row or any(value is None for value in row.values()):
                raise ValueError()
            key, title = row["id"].strip(), row["title"].strip()
            if not 1 <= len(key) <= 120 or not 1 <= len(title) <= 240 or key in result:
                raise ValueError()
            day = date.fromisoformat(row["date"].strip()).isoformat()
            if row["date"].strip() != day or row["status"].strip() not in KINDS[kind]:
                raise ValueError()
            cents = 0
            if kind == "receipts":
                amount = Decimal(row["amount_eur"].strip().replace(",", "."))
                if not amount.is_finite() or amount < 0 or amount > 10**9:
                    raise ValueError()
                cents = amount * 100
                if cents != cents.to_integral_value():
                    raise ValueError()
            result[key] = (kind, key, title, day, row["status"].strip(), int(cents))
        except (ValueError, InvalidOperation) as error:
            raise ValueError(f"Ligne {reader.line_num} invalide ou identifiant en double.") from error
        if len(result) > 5000:
            raise ValueError("L’import est limité à 5 000 lignes.")
    if not result:
        raise ValueError("Le fichier ne contient aucune ligne de données.")
    return result.values()


class BusinessImports:
    def __init__(self, path):
        self.path = path
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS business_items (
                    kind TEXT NOT NULL, id TEXT NOT NULL, title TEXT NOT NULL,
                    day TEXT NOT NULL, status TEXT NOT NULL, cents INTEGER NOT NULL,
                    PRIMARY KEY(kind, id)
                );
                CREATE TABLE IF NOT EXISTS local_appointments (
                    id TEXT PRIMARY KEY, clock TEXT NOT NULL, duration INTEGER NOT NULL,
                    utc_start TEXT NOT NULL, utc_end TEXT NOT NULL, note TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS appointment_links (
                    appointment_id TEXT PRIMARY KEY, target_kind TEXT NOT NULL, target_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS business_import_runs (
                    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL,
                    count INTEGER NOT NULL, detail TEXT NOT NULL,
                    happened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS ticket_activity (
                    id INTEGER PRIMARY KEY, ticket_id TEXT NOT NULL, status TEXT NOT NULL,
                    source_status TEXT NOT NULL, note TEXT NOT NULL, actor TEXT NOT NULL,
                    happened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS ticket_activity_by_ticket ON ticket_activity(ticket_id,id DESC);
                CREATE VIEW IF NOT EXISTS effective_business_items AS
                    SELECT b.kind, b.id, b.title, b.day,
                           CASE WHEN a.source_status=b.status THEN a.status ELSE b.status END AS status,
                           b.cents, b.status AS source_status
                    FROM business_items b LEFT JOIN ticket_activity a
                    ON b.kind='tickets' AND a.id=(
                        SELECT MAX(id) FROM ticket_activity WHERE ticket_id=b.id
                    );
                CREATE TABLE IF NOT EXISTS business_folder_files (
                    kind TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, run_id INTEGER NOT NULL
                );
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def import_csv(self, kind, content):
        state = self.apply(kind, content)
        if state["state"] == "error":
            raise ValueError(state["detail"])
        return {"count": state["count"]}

    def apply(self, kind, content, fingerprint=None, error=None):
        rows = ()
        if error is None:
            try:
                rows = parse_rows(kind, content)
            except (ValueError, csv.Error) as exc:
                error = str(exc) if isinstance(exc, ValueError) else "Format CSV invalide."
        state = "error" if error else "ok"
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if fingerprint is not None:
                previous = db.execute("""
                    SELECT r.state, r.count, r.detail FROM business_folder_files f
                    JOIN business_import_runs r ON r.id=f.run_id WHERE f.kind=? AND f.fingerprint=?
                """, (kind, fingerprint)).fetchone()
                if previous:
                    return {**dict(previous), "unchanged": True}
            if not error and kind == "appointments":
                local_ids = {row[0] for row in db.execute("SELECT id FROM local_appointments")}
                if any(row[1] in local_ids for row in rows):
                    error = "Un identifiant appartient à un rendez-vous saisi dans ORION."
                    state, rows = "error", ()
            if not error:
                if kind == "tickets":
                    for _, key, _, _, new_status, _ in rows:
                        previous = db.execute("SELECT status FROM business_items WHERE kind='tickets' AND id=?",
                                              (key,)).fetchone()
                        if previous and previous["status"] != new_status:
                            db.execute("""
                                INSERT INTO ticket_activity(ticket_id,status,source_status,note,actor)
                                VALUES (?,?,?,'Statut mis à jour par l’import CSV.','Import CSV')
                            """, (key, new_status, new_status))
                db.executemany("""
                    INSERT INTO business_items VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(kind,id) DO UPDATE SET
                        title=excluded.title, day=excluded.day, status=excluded.status, cents=excluded.cents
                """, rows)
            run = db.execute("INSERT INTO business_import_runs(kind,state,count,detail) VALUES (?, ?, ?, ?)",
                             (kind, state, len(rows), error or ""))
            if fingerprint is not None:
                db.execute("""
                    INSERT INTO business_folder_files VALUES (?, ?, ?)
                    ON CONFLICT(kind) DO UPDATE SET fingerprint=excluded.fingerprint, run_id=excluded.run_id
                """, (kind, fingerprint, run.lastrowid))
        return {"state": state, "count": len(rows), "detail": error or "", "unchanged": False}

    def sync_folder(self, directory):
        files = {}
        for kind in KINDS:
            filename = kind + ".csv"
            path = directory / filename
            try:
                if path.is_symlink():
                    raise OSError("Lien symbolique.")
                stat = path.stat()
                if not path.is_file():
                    raise OSError("Fichier ordinaire attendu.")
                with path.open("rb") as file:
                    payload = file.read(MAX_FILE_BYTES + 1)
                current = path.stat()
                if (stat.st_size, stat.st_mtime_ns, stat.st_ino) != (
                    current.st_size, current.st_mtime_ns, current.st_ino
                ):
                    files[filename] = {"state": "error", "detail": "Fichier modifié pendant la lecture. Réessayez."}
                    continue
            except FileNotFoundError:
                with closing(self.connect()) as db:
                    tracked = db.execute("SELECT 1 FROM business_folder_files WHERE kind=?", (kind,)).fetchone()
                if tracked:
                    files[filename] = {"state": "error", "detail": "Fichier auparavant importé, désormais absent."}
                continue
            except OSError:
                files[filename] = {"state": "error", "detail": "Impossible de lire ce fichier local."}
                continue
            fingerprint = hashlib.sha256(payload).hexdigest()
            if len(payload) > MAX_FILE_BYTES:
                result = self.apply(kind, "", fingerprint, "Le CSV dépasse 2 Mo.")
            else:
                try:
                    content = payload.decode("utf-8-sig")
                except UnicodeDecodeError:
                    result = self.apply(kind, "", fingerprint, "Le CSV doit être encodé en UTF-8.")
                else:
                    result = self.apply(kind, content, fingerprint)
            files[filename] = result
        return files

    def latest(self):
        with closing(self.connect()) as db:
            return {row["kind"]: dict(row) for row in db.execute("""
                SELECT r.kind, r.state, r.count, r.detail, r.happened_at,
                       (SELECT max(ok.happened_at) FROM business_import_runs ok
                        WHERE ok.kind=r.kind AND ok.state='ok') AS last_success
                FROM business_import_runs r WHERE r.id IN (SELECT MAX(id) FROM business_import_runs GROUP BY kind)
            """)}

    def open_tickets(self):
        with closing(self.connect()) as db:
            row = db.execute("""
                SELECT COUNT(*) AS active, COUNT(CASE WHEN status='urgent' THEN 1 END) AS urgent
                FROM effective_business_items WHERE kind='tickets' AND status IN ('open','urgent')
            """).fetchone()
        return dict(row)

    def finances(self, today, days, status, limit, offset):
        start = today - timedelta(days=days - 1)
        previous_start = start - timedelta(days=days)
        with closing(self.connect()) as db:
            db.execute("BEGIN")
            metrics = db.execute("""
                SELECT
                    count(CASE WHEN day>=? THEN 1 END) AS records,
                    coalesce(sum(CASE WHEN day>=? AND status='paid' THEN cents END),0) AS paid,
                    coalesce(sum(CASE WHEN day>=? AND status='pending' THEN cents END),0) AS pending,
                    coalesce(sum(CASE WHEN day<? AND status='paid' THEN cents END),0) AS previous_paid
                FROM business_items WHERE kind='receipts' AND day BETWEEN ? AND ?
            """, (start.isoformat(), start.isoformat(), start.isoformat(), start.isoformat(),
                  previous_start.isoformat(), today.isoformat())).fetchone()
            rows = db.execute("""
                SELECT id, title, day, status, cents FROM business_items
                WHERE kind='receipts' AND day BETWEEN ? AND ? AND (?='all' OR status=?)
                ORDER BY day DESC, id LIMIT ? OFFSET ?
            """, (start.isoformat(), today.isoformat(), status, status, limit + 1, offset)).fetchall()
            source = db.execute("""
                SELECT state, happened_at, detail,
                    (SELECT MAX(happened_at) FROM business_import_runs
                     WHERE kind='receipts' AND state='ok') AS last_success
                FROM business_import_runs WHERE kind='receipts' ORDER BY id DESC LIMIT 1
            """).fetchone()
        return {"start": start.isoformat(), "end": today.isoformat(), "metrics": dict(metrics),
                "items": [dict(row) for row in rows[:limit]], "has_more": len(rows) > limit,
                "source": dict(source) if source else None}

    def summary(self, today, cutoff):
        day = today.isoformat()
        with closing(self.connect()) as db:
            row = db.execute("""
                SELECT
                    count(CASE WHEN kind='prospects' AND status='new' AND day=? THEN 1 END) AS prospects,
                    count(CASE WHEN kind='appointments' AND status='scheduled' AND day BETWEEN ? AND ? THEN 1 END) AS appointments,
                    count(CASE WHEN kind='tickets' AND status IN ('open','urgent') THEN 1 END) AS tickets,
                    coalesce(sum(CASE WHEN kind='receipts' AND status='paid' AND day=? THEN cents END),0) AS receipts
                FROM effective_business_items
            """, (day, day, cutoff.isoformat(), day)).fetchone()
            priority = [dict(item) for item in db.execute("""
                SELECT kind, id, title, day, status,
                    (kind='appointments' AND EXISTS (SELECT 1 FROM local_appointments a
                                                     WHERE a.id=effective_business_items.id)) AS local_appointment
                FROM effective_business_items
                WHERE (kind='prospects' AND status='new' AND day<=?)
                   OR (kind='appointments' AND status='scheduled' AND day BETWEEN ? AND ?)
                   OR (kind='tickets' AND status IN ('open','urgent'))
            """, (day, day, cutoff.isoformat()))]
        return dict(row), priority
