"""Boîte de réception et classement dans la base locale ORION."""
import sqlite3
from contextlib import closing
from uuid import uuid4

from .wedding_notes import searchable


class Inbox:
    def __init__(self, path):
        self.path = path
        with closing(self.connect()) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS inbox_entries (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
                    content TEXT NOT NULL, source TEXT NOT NULL, source_date TEXT,
                    target_kind TEXT, target_id TEXT, due_date TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

            db.executescript("""
                CREATE TABLE IF NOT EXISTS inbox_owners (
                    entry_id TEXT PRIMARY KEY, owner TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS inbox_files (
                    entry_id TEXT PRIMARY KEY, filename TEXT NOT NULL, mime TEXT NOT NULL,
                    payload BLOB NOT NULL
                );
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def save(self, data, entry_id=None, *, owner=None, attachment=None):
        fields = ("kind", "title", "content", "source", "source_date", "target_kind", "target_id", "due_date")
        values = tuple(data[field] for field in fields)
        with closing(self.connect()) as db, db:
            if entry_id is None:
                entry_id = uuid4().hex
                db.execute("""
                    INSERT INTO inbox_entries
                    (id, kind, title, content, source, source_date, target_kind, target_id, due_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (entry_id, *values))
                if owner is not None:
                    db.execute("INSERT INTO inbox_owners VALUES (?, ?)", (entry_id, owner))
                if attachment is not None:
                    db.execute("INSERT INTO inbox_files VALUES (?, ?, ?, ?)", (entry_id, *attachment))
            else:
                updated = db.execute("""
                    UPDATE inbox_entries SET kind=?, title=?, content=?, source=?, source_date=?,
                        target_kind=?, target_id=?, due_date=?, updated_at=CURRENT_TIMESTAMP WHERE id=?
                    AND (? IS NULL OR id IN (SELECT entry_id FROM inbox_owners WHERE owner=?))
                """, (*values, entry_id, owner, owner))
                if not updated.rowcount:
                    raise KeyError("Élément introuvable.")
        return entry_id

    def search(self, query, kind, scope, limit, offset, owner=None):
        filters, args = ["1=1"], []
        if owner is not None:
            filters.append("e.id IN (SELECT entry_id FROM inbox_owners WHERE owner=?)")
            args.append(owner)
        if kind:
            filters.append("kind=?")
            args.append(kind)
        if scope == "unfiled":
            filters.append("target_id IS NULL")
        elif scope:
            target_kind, target_id = scope.split(":", 1)
            filters.append("target_kind=? AND target_id=?")
            args.extend((target_kind, target_id))
        terms = dict.fromkeys(searchable(query).split())
        for term in terms:
            filters.append("instr(normalized(title || ' ' || content || ' ' || source), ?) > 0")
            args.append(term)
        where = " AND ".join(filters)
        with closing(self.connect()) as db:
            db.create_function("normalized", 1, searchable, deterministic=True)
            rows = db.execute(f"""
                SELECT e.*, f.filename FROM inbox_entries e
                LEFT JOIN inbox_files f ON e.id=f.entry_id WHERE {where}
                ORDER BY updated_at DESC, e.rowid DESC LIMIT ? OFFSET ?
            """, (*args, limit + 1, offset)).fetchall()
        return {"items": [dict(row) for row in rows[:limit]], "has_more": len(rows) > limit}

    def attachment(self, entry_id, owner):
        with closing(self.connect()) as db:
            row = db.execute("""
                SELECT filename, mime, payload FROM inbox_files WHERE entry_id=?
                AND (? IS NULL OR entry_id IN (SELECT entry_id FROM inbox_owners WHERE owner=?))
            """, (entry_id, owner, owner)).fetchone()
        if row is None:
            raise KeyError("Pièce jointe introuvable.")
        return dict(row)

    def linked_project(self, key):
        with closing(self.connect()) as db:
            rows = db.execute("""
                SELECT id, kind, title, source_date, due_date FROM inbox_entries
                WHERE target_kind='project' AND target_id=?
                ORDER BY updated_at DESC, rowid DESC LIMIT 11
            """, (key,)).fetchall()
        return {"items": [dict(row) for row in rows[:10]], "has_more": len(rows) > 10}

    def due_before(self, cutoff):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("""
                SELECT id, title, due_date FROM inbox_entries
                WHERE due_date<=? ORDER BY due_date, rowid
            """, (cutoff.isoformat(),))]

    def get(self, entry_id, owner):
        with closing(self.connect()) as db:
            row = db.execute("""
                SELECT e.*, f.filename FROM inbox_entries e LEFT JOIN inbox_files f ON e.id=f.entry_id
                WHERE e.id=? AND (? IS NULL OR e.id IN (SELECT entry_id FROM inbox_owners WHERE owner=?))
            """, (entry_id, owner, owner)).fetchone()
            if row is None:
                raise KeyError("Élément introuvable.")
            return dict(row)

    def export(self, owner=None):
        with closing(self.connect()) as db:
            return [dict(row) for row in db.execute("""
                SELECT e.*, f.filename FROM inbox_entries e LEFT JOIN inbox_files f ON e.id=f.entry_id
                WHERE (? IS NULL OR e.id IN (SELECT entry_id FROM inbox_owners WHERE owner=?)) ORDER BY e.rowid
            """, (owner, owner))]
