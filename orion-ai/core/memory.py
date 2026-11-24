import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4


class Memory:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY, task TEXT NOT NULL, agents TEXT NOT NULL,
                    status TEXT NOT NULL, steps TEXT NOT NULL,
                    error TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            db.execute("""
                CREATE TABLE IF NOT EXISTS wedding_workflow_sources (
                    workflow_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, sources TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS wedding_workflows_by_plan ON wedding_workflow_sources(plan_id)")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def create(self, task, agents, plan_id=None, sources=()):
        workflow_id = uuid4().hex
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO workflows (id, task, agents, status, steps) VALUES (?, ?, ?, ?, ?)",
                       (workflow_id, task, json.dumps(agents), "running", "[]"))
            if plan_id is not None:
                db.execute("INSERT INTO wedding_workflow_sources VALUES (?, ?, ?)",
                           (workflow_id, plan_id, json.dumps(sources, ensure_ascii=False)))
        return workflow_id

    def save(self, workflow_id, steps, status="running", error=None):
        with closing(self._connect()) as db, db:
            db.execute("UPDATE workflows SET steps=?, status=?, error=? WHERE id=?",
                       (json.dumps(steps, ensure_ascii=False), status, error, workflow_id))

    def get(self, workflow_id, plan_id=None):
        with closing(self._connect()) as db:
            row = db.execute("""
                SELECT w.*, s.sources FROM workflows w
                LEFT JOIN wedding_workflow_sources s ON s.workflow_id=w.id
                WHERE w.id=? AND s.plan_id IS ?
            """, (workflow_id, plan_id)).fetchone()
        if row is None:
            return None
        result = dict(row)
        for field in ("steps", "agents"):
            result[field] = json.loads(result[field])
        sources = result.pop("sources")
        if sources is not None:
            result["sources"] = json.loads(sources)
        return result

    def wedding_history(self, plan_id):
        with closing(self._connect()) as db:
            return [dict(row) for row in db.execute("""
                SELECT w.id, w.status, w.created_at FROM wedding_workflow_sources s
                JOIN workflows w ON w.id=s.workflow_id WHERE s.plan_id=?
                ORDER BY w.created_at DESC, w.rowid DESC LIMIT 30
            """, (plan_id,))]

    def documents(self):
        with closing(self._connect()) as db:
            rows = db.execute(
                """SELECT id, task, steps FROM workflows WHERE status IN ('completed', 'failed')
                AND NOT EXISTS (SELECT 1 FROM wedding_workflow_sources WHERE workflow_id=workflows.id)"""
            )
            for row in rows:
                for number, step in enumerate(json.loads(row["steps"]), 1):
                    if step["result"]:
                        yield (
                            f'{row["id"]}:{number}',
                            f'{row["task"]}\n\n{step["result"]}',
                            {"workflow_id": row["id"], "agent": step["agent"], "step": number},
                        )
