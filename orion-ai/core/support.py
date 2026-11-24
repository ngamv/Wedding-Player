"""Suivi des tickets importés et tickets saisis dans ORION."""
from contextlib import closing
from uuid import uuid4


class Support:
    def __init__(self, business):
        self.business = business

    def list(self, status, limit, offset):
        with closing(self.business.connect()) as db:
            rows = db.execute("""
                SELECT id, title, day, status FROM effective_business_items
                WHERE kind='tickets' AND
                    (?='all' OR (?='active' AND status IN ('open','urgent')) OR status=?)
                ORDER BY CASE status WHEN 'urgent' THEN 0 WHEN 'open' THEN 1 ELSE 2 END, day, id
                LIMIT ? OFFSET ?
            """, (status, status, status, limit + 1, offset)).fetchall()
        return {"items": [dict(row) for row in rows[:limit]], "has_more": len(rows) > limit}

    @staticmethod
    def read(db, key):
        row = db.execute("SELECT * FROM effective_business_items WHERE kind='tickets' AND id=?", (key,)).fetchone()
        if row is None:
            raise KeyError("Ticket introuvable.")
        timeline = db.execute("""
            SELECT status, note, actor, happened_at FROM ticket_activity
            WHERE ticket_id=? ORDER BY id DESC LIMIT 30
        """, (key,))
        return {**dict(row), "history": [dict(event) for event in timeline]}

    def get(self, key):
        with closing(self.business.connect()) as db:
            db.execute("BEGIN")
            return self.read(db, key)

    def create(self, title, day, status, note, actor):
        key = "orion-" + uuid4().hex
        with closing(self.business.connect()) as db, db:
            db.execute("INSERT INTO business_items VALUES ('tickets', ?, ?, ?, ?, 0)",
                       (key, title, day, status))
            self.write(db, key, status, status, note, actor)
            return self.read(db, key)

    @staticmethod
    def write(db, key, status, source, note, actor):
        db.execute("""
            INSERT INTO ticket_activity(ticket_id,status,source_status,note,actor) VALUES (?,?,?,?,?)
        """, (key, status, source, note, actor))

    def update(self, key, status, note, actor):
        with closing(self.business.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = self.read(db, key)
            self.write(db, key, status, row["source_status"], note, actor)
            return self.read(db, key)
