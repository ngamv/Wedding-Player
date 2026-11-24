"""Comptes locaux pour la boîte de réception."""
import hashlib
import hmac
import re
import secrets
from contextlib import closing


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600000)


class InboxAccounts:
    def __init__(self, inbox):
        self.inbox = inbox
        with closing(inbox.connect()) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS inbox_accounts (
                    username TEXT PRIMARY KEY, salt BLOB NOT NULL, secret BLOB NOT NULL,
                    role TEXT NOT NULL
                )
            """)

    def enabled(self):
        with closing(self.inbox.connect()) as db:
            return bool(db.execute("SELECT 1 FROM inbox_accounts LIMIT 1").fetchone())

    def add(self, username, password, role):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]{1,64}", username) or not re.fullmatch(r"[ -~]{12,256}", password):
            raise ValueError("Identifiant alphanumérique et mot de passe de 12 à 256 caractères ASCII imprimables requis.")
        if role not in ("admin", "member"):
            raise ValueError("Rôle inconnu.")
        salt = secrets.token_bytes(16)
        with closing(self.inbox.connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if role != "admin" and not db.execute("SELECT 1 FROM inbox_accounts WHERE role='admin'").fetchone():
                raise ValueError("Créez d’abord un compte administrateur.")
            db.execute("INSERT INTO inbox_accounts VALUES (?, ?, ?, ?)", (
                username, salt, password_hash(password, salt), role,
            ))

    def verify(self, username, password):
        if len(username) > 64 or len(password) > 256:
            return None
        with closing(self.inbox.connect()) as db:
            row = db.execute("SELECT role, salt, secret FROM inbox_accounts WHERE username=?", (username,)).fetchone()
        salt = row["salt"] if row else b"\x00" * 16
        candidate = password_hash(password, salt)
        if row and hmac.compare_digest(candidate, row["secret"]):
            return row["role"]
        return None
