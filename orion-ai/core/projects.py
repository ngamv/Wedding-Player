"""Registre et historique des projets locaux."""
import sqlite3
from contextlib import closing
from datetime import timedelta
from uuid import uuid4


class Projects:
    def __init__(self, path):
        self.path = path
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, owner TEXT NOT NULL,
                    due TEXT, status TEXT NOT NULL, note TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS project_events (
                    id INTEGER PRIMARY KEY, project_id TEXT NOT NULL, status TEXT NOT NULL,
                    note TEXT NOT NULL, actor TEXT NOT NULL,
                    happened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS project_events_project ON project_events(project_id,id DESC);
                CREATE TABLE IF NOT EXISTS project_tasks (
                    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, title TEXT NOT NULL, owner TEXT NOT NULL,
                    due TEXT, status TEXT NOT NULL, note TEXT NOT NULL,
                    updated_by TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS project_tasks_project ON project_tasks(project_id);
                CREATE TABLE IF NOT EXISTS project_task_dependencies (
                    task_id TEXT NOT NULL, prerequisite_id TEXT NOT NULL,
                    PRIMARY KEY(task_id, prerequisite_id)
                );
                CREATE INDEX IF NOT EXISTS project_task_prerequisite ON project_task_dependencies(prerequisite_id);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def list(self, status="all"):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("""
                SELECT * FROM projects WHERE ?='all' OR status=?
                ORDER BY CASE status WHEN 'blocked' THEN 0 WHEN 'done' THEN 2 ELSE 1 END,
                         due IS NULL, due, title, id
            """, (status, status))]

    def planning(self, today, mode, owner, limit, offset):
        day = today.isoformat()
        end = (today + timedelta(days=7)).isoformat()
        cte = """
            WITH tasks AS (
                SELECT t.id, t.project_id, p.title AS project_title, t.title, t.owner, t.due, t.status,
                       (t.status='blocked' OR EXISTS (
                           SELECT 1 FROM project_task_dependencies d
                           JOIN project_tasks prerequisite ON prerequisite.id=d.prerequisite_id
                           WHERE d.task_id=t.id AND prerequisite.status<>'done'
                       )) AS blocked
                FROM project_tasks t JOIN projects p ON p.id=t.project_id
                WHERE t.status<>'done' AND p.status<>'done'
            )
        """
        predicates = {
            "all": ("1=1", ()), "overdue": ("due<?", (day,)),
            "upcoming": ("due BETWEEN ? AND ?", (day, end)),
            "blocked": ("blocked", ()), "undated": ("due IS NULL", ()),
        }
        condition, args = predicates[mode]
        with closing(self.connect()) as db:
            db.execute("BEGIN")
            owners = [row[0] for row in db.execute(cte + "SELECT DISTINCT owner FROM tasks ORDER BY owner")]
            counts = db.execute(cte + """
                SELECT COUNT(*) AS total,
                       COUNT(CASE WHEN due<? THEN 1 END) AS overdue,
                       COUNT(CASE WHEN due BETWEEN ? AND ? THEN 1 END) AS upcoming,
                       COUNT(CASE WHEN blocked THEN 1 END) AS blocked,
                       COUNT(CASE WHEN due IS NULL THEN 1 END) AS undated
                FROM tasks WHERE (?='' OR owner=?)
            """, (day, day, end, owner, owner)).fetchone()
            rows = db.execute(cte + f"""
                SELECT * FROM tasks WHERE ({condition}) AND (?='' OR owner=?)
                ORDER BY due IS NULL, due, blocked DESC, project_title, id LIMIT ? OFFSET ?
            """, (*args, owner, owner, limit+1, offset)).fetchall()
        return {"date": day, "until": end, "owners": owners, "counts": dict(counts),
                "items": [dict(row) for row in rows[:limit]], "has_more": len(rows)>limit}

    def priorities(self, today, cutoff):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("""
                WITH task_counts AS (
                    SELECT project_id,
                           COUNT(CASE WHEN status='blocked' THEN 1 END) AS blocked_tasks,
                           COUNT(CASE WHEN due<? THEN 1 END) AS late_tasks,
                           COUNT(CASE WHEN due BETWEEN ? AND ? THEN 1 END) AS upcoming_tasks,
                           MIN(CASE WHEN due<=? THEN due END) AS task_due,
                           COUNT(CASE WHEN (due<=? OR status='blocked') AND EXISTS (
                               SELECT 1 FROM project_task_dependencies d
                               JOIN project_tasks p ON p.id=d.prerequisite_id
                               WHERE d.task_id=project_tasks.id AND p.status<>'done'
                           ) THEN 1 END) AS waiting_tasks
                    FROM project_tasks WHERE status<>'done' GROUP BY project_id
                )
                SELECT p.*, COALESCE(t.blocked_tasks,0) AS blocked_tasks,
                       COALESCE(t.late_tasks,0) AS late_tasks, COALESCE(t.upcoming_tasks,0) AS upcoming_tasks,
                       t.task_due, COALESCE(t.waiting_tasks,0) AS waiting_tasks
                FROM projects p LEFT JOIN task_counts t ON t.project_id=p.id
                WHERE p.status<>'done' AND
                    (p.status='blocked' OR p.due<=? OR t.blocked_tasks>0 OR t.task_due IS NOT NULL)
            """, (today.isoformat(), today.isoformat(), cutoff.isoformat(),
                  cutoff.isoformat(), cutoff.isoformat(), cutoff.isoformat()))]

    @staticmethod
    def read(db, key):
        row = db.execute("SELECT * FROM projects WHERE id=?", (key,)).fetchone()
        if row is None:
            raise KeyError("Projet introuvable.")
        events = db.execute("""
            SELECT status, note, actor, happened_at FROM project_events
            WHERE project_id=? ORDER BY id DESC LIMIT 30
        """, (key,))
        tasks = db.execute("""
            SELECT * FROM project_tasks WHERE project_id=?
            ORDER BY CASE status WHEN 'blocked' THEN 0 WHEN 'done' THEN 2 ELSE 1 END,
                     due IS NULL, due, title, id
        """, (key,))
        tasks = {task["id"]: {**dict(task), "dependencies": [], "waiting_for": []} for task in tasks}
        for edge in db.execute("""
            SELECT d.task_id, d.prerequisite_id FROM project_task_dependencies d
            JOIN project_tasks t ON t.id=d.task_id WHERE t.project_id=? ORDER BY d.prerequisite_id
        """, (key,)):
            task = tasks[edge["task_id"]]
            prerequisite = tasks[edge["prerequisite_id"]]
            task["dependencies"].append(prerequisite["id"])
            if prerequisite["status"] != "done":
                task["waiting_for"].append(prerequisite["id"])
        return {**dict(row), "history": [dict(event) for event in events], "tasks": list(tasks.values())}

    def require(self, key):
        with closing(self.connect()) as db:
            if db.execute("SELECT 1 FROM projects WHERE id=?", (key,)).fetchone() is None:
                raise KeyError("Projet introuvable.")

    def get(self, key):
        with closing(self.connect()) as db:
            db.execute("BEGIN")
            return self.read(db, key)

    def save(self, data, actor, key=None):
        values = tuple(data[field] for field in ("title", "owner", "due", "status", "note"))
        with closing(self.connect()) as db, db:
            if key is None:
                key = uuid4().hex
                db.execute("INSERT INTO projects VALUES (?,?,?,?,?,?)", (key, *values))
            else:
                updated = db.execute("""
                    UPDATE projects SET title=?, owner=?, due=?, status=?, note=? WHERE id=?
                """, (*values, key))
                if not updated.rowcount:
                    raise KeyError("Projet introuvable.")
            db.execute("INSERT INTO project_events(project_id,status,note,actor) VALUES (?,?,?,?)",
                       (key, data["status"], data["note"], actor))
            return self.read(db, key)


    def save_task(self, project, data, actor, key=None, dependencies=None):
        values = tuple(data[field] for field in ("title", "owner", "due", "status", "note"))
        with closing(self.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM projects WHERE id=?", (project,)).fetchone()
            if row is None:
                raise KeyError("Projet introuvable.")
            if key is None:
                key = uuid4().hex
                db.execute("""
                    INSERT INTO project_tasks(id,project_id,title,owner,due,status,note,updated_by)
                    VALUES (?,?,?,?,?,?,?,?)
                """, (key, project, *values, actor))
            else:
                updated = db.execute("""
                    UPDATE project_tasks SET title=?, owner=?, due=?, status=?, note=?,
                        updated_by=?, updated_at=CURRENT_TIMESTAMP WHERE id=? AND project_id=?
                """, (*values, actor, key, project))
                if not updated.rowcount:
                    raise KeyError("Tâche introuvable dans ce projet.")
            if dependencies is not None:
                self.set_dependencies(db, project, key, dependencies)
            waiting = db.execute("""
                SELECT 1 FROM project_task_dependencies d JOIN project_tasks p ON p.id=d.prerequisite_id
                WHERE d.task_id=? AND p.status<>'done' LIMIT 1
            """, (key,)).fetchone()
            if data["status"] == "done" and waiting:
                raise ValueError("Terminez les prérequis avant de clôturer cette tâche.")
            if data["status"] != "done" and db.execute("""
                SELECT 1 FROM project_task_dependencies d JOIN project_tasks t ON t.id=d.task_id
                WHERE d.prerequisite_id=? AND t.status='done' LIMIT 1
            """, (key,)).fetchone():
                raise ValueError("Rouvrez d’abord les tâches terminées qui dépendent de celle-ci.")
            return self.read(db, project)

    @staticmethod
    def set_dependencies(db, project, key, dependencies):
        valid = {row[0] for row in db.execute("SELECT id FROM project_tasks WHERE project_id=?", (project,))}
        if key in dependencies or not set(dependencies) <= valid or len(set(dependencies)) != len(dependencies):
            raise ValueError("Choisissez des prérequis distincts dans le même projet.")
        db.execute("DELETE FROM project_task_dependencies WHERE task_id=?", (key,))
        db.executemany("INSERT INTO project_task_dependencies VALUES (?,?)",
                       [(key, prerequisite) for prerequisite in dependencies])
        cycle = db.execute("""
            WITH RECURSIVE upstream(id) AS (
                SELECT prerequisite_id FROM project_task_dependencies WHERE task_id=?
                UNION
                SELECT d.prerequisite_id FROM project_task_dependencies d JOIN upstream u ON d.task_id=u.id
            )
            SELECT 1 FROM upstream WHERE id=?
        """, (key, key)).fetchone()
        if cycle:
            raise ValueError("Cette dépendance créerait une boucle.")
