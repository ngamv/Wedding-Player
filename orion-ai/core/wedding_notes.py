"""Mémoire locale d'un dossier mariage."""
import unicodedata
from contextlib import closing
from datetime import datetime, timezone
from uuid import uuid4


def searchable(value):
    return "".join(c for c in unicodedata.normalize("NFD", value.casefold())
                   if unicodedata.category(c) != "Mn")


class WeddingNotes:
    def __init__(self, checklist):
        self.checklist = checklist
        with closing(checklist.connect()) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS wedding_notes (
                    plan TEXT NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL,
                    title TEXT NOT NULL, content TEXT NOT NULL, source TEXT NOT NULL,
                    task_id INTEGER, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(plan, id)
                )
            """)

    def search(self, plan_id, query, kind, limit, offset):
        self.checklist.get(plan_id)
        filters = ["plan=?"]
        args = [plan_id]
        if kind:
            filters.append("kind=?")
            args.append(kind)
        for term in dict.fromkeys(searchable(query).split()):
            filters.append("instr(normalized(title || ' ' || content || ' ' || source), ?) > 0")
            args.append(term)
        where = " AND ".join(filters)
        with closing(self.checklist.connect()) as db:
            db.create_function("normalized", 1, searchable, deterministic=True)
            rows = db.execute(f"""
                SELECT id, kind, title, content, source, task_id, created_at, updated_at
                FROM wedding_notes WHERE {where}
                ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?
            """, (*args, limit + 1, offset)).fetchall()
        return {"notes": [dict(row) for row in rows[:limit]], "has_more": len(rows) > limit}

    def selected(self, plan_id, ids):
        self.checklist.get(plan_id)
        with closing(self.checklist.connect()) as db:
            placeholders = ", ".join("?" for _ in ids)
            rows = db.execute(f"""
                SELECT id, title, kind, content, source, updated_at
                FROM wedding_notes WHERE plan=? AND id IN ({placeholders})
            """, (plan_id, *ids))
            notes = {row["id"]: dict(row) for row in rows}
        if len(notes) != len(ids):
            raise ValueError("Les sources doivent être distinctes et appartenir au dossier.")
        selected = [notes[key] for key in ids]
        if sum(len(note["content"]) for note in selected) > 24000:
            raise ValueError("Sélectionnez au maximum 24 000 caractères de notes.")
        return selected

    def save(self, plan_id, data, note_id=None):
        plan = self.checklist.get(plan_id)
        if data["task_id"] is not None and not any(t["id"] == data["task_id"] for t in plan["tasks"]):
            raise ValueError("La tâche doit appartenir au dossier sélectionné.")
        now = datetime.now(timezone.utc).isoformat()
        values = tuple(data[key] for key in ("kind", "title", "content", "source", "task_id"))
        with closing(self.checklist.connect()) as db, db:
            if note_id is None:
                note_id = uuid4().hex
                db.execute("""
                    INSERT INTO wedding_notes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (plan_id, note_id, *values, now, now))
            else:
                changed = db.execute("""
                    UPDATE wedding_notes SET kind=?, title=?, content=?, source=?, task_id=?, updated_at=?
                    WHERE plan=? AND id=?
                """, (*values, now, plan_id, note_id))
                if not changed.rowcount:
                    raise KeyError("Note introuvable dans ce dossier.")
        return note_id
