"""File persistante pour la génération locale du brief du CEO."""
import logging
import sqlite3
from contextlib import closing
from datetime import date


class CEOJobs:
    def __init__(self, path):
        self.path = path
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS ceo_jobs (
                    id INTEGER PRIMARY KEY,
                    day TEXT NOT NULL, origin TEXT NOT NULL, state TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    queued_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TEXT, finished_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS ceo_job_active ON ceo_jobs(day)
                    WHERE state IN ('queued', 'running');
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def expire(db):
        db.execute("""
            UPDATE ceo_jobs SET state='failed', detail='Exécution interrompue ou délai dépassé.',
                                finished_at=CURRENT_TIMESTAMP
            WHERE state='running' AND started_at < datetime('now', '-15 minutes')
        """)

    def enqueue(self, day, origin):
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self.expire(db)
            key = day.isoformat()
            active = db.execute("""
                SELECT * FROM ceo_jobs WHERE day=? AND state IN ('queued','running')
            """, (key,)).fetchone()
            if active is not None:
                return dict(active)
            row = db.execute("""
                INSERT INTO ceo_jobs(day,origin,state) VALUES (?,?,'queued') RETURNING *
            """, (key, origin)).fetchone()
            return dict(row)

    def list(self):
        with closing(self.connect()) as db, db:
            self.expire(db)
            return [dict(row) for row in db.execute("""
                SELECT * FROM (
                    SELECT * FROM ceo_jobs ORDER BY (state IN ('queued','running')) DESC, id DESC LIMIT 15
                ) ORDER BY id DESC
            """)]

    def run(self, job_id, generate):
        with closing(self.connect()) as db, db:
            row = db.execute("""
                UPDATE ceo_jobs SET state='running', started_at=CURRENT_TIMESTAMP
                WHERE id=? AND state='queued' RETURNING day
            """, (job_id,)).fetchone()
        if row is None:
            return None
        report = None
        try:
            report = generate(date.fromisoformat(row["day"]))
            problems = [name for name, flag in report["sources"].items() if flag == "error"]
            problems.extend(name for name, result in report["file_sync"].items() if result["state"] == "error")
            detail = "Sources à vérifier · " + ", ".join(problems) if problems else ""
        except Exception:
            logging.getLogger(__name__).exception("Échec du brief CEO, exécution %s", job_id)
            detail = "Génération impossible. Consultez les journaux ORION."
        with closing(self.connect()) as db, db:
            db.execute("""
                UPDATE ceo_jobs SET state=?, detail=?, finished_at=CURRENT_TIMESTAMP
                WHERE id=? AND state='running'
            """, ("failed" if detail else "completed", detail, job_id))
        return report
