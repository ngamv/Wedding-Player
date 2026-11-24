"""Identifiant réservé à l’automatisation du rapport Wedding."""
import hashlib
import hmac
import sqlite3
from contextlib import closing

USERNAME = "orion-n8n-wedding"


def configure(path, token):
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS wedding_service_token (id INTEGER PRIMARY KEY, digest TEXT NOT NULL)")
        db.execute("""
            INSERT INTO wedding_service_token VALUES (1,?)
            ON CONFLICT(id) DO UPDATE SET digest=excluded.digest
        """, (hashlib.sha256(token.encode("ascii")).hexdigest(),))


def authorized(path, token):
    if not token or not token.isascii() or len(token) > 128:
        return False
    with closing(sqlite3.connect(path, timeout=10)) as db:
        exists = db.execute("SELECT 1 FROM sqlite_schema WHERE name='wedding_service_token' AND type='table'").fetchone()
        if not exists:
            return False
        row = db.execute("SELECT digest FROM wedding_service_token WHERE id=1").fetchone()
    return bool(row and hmac.compare_digest(row[0], hashlib.sha256(token.encode("ascii")).hexdigest()))
