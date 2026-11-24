"""Sessions temporaires du tableau de bord local."""
from secrets import token_urlsafe
from threading import Lock
from time import monotonic

SESSION_LIFETIME = 8 * 60 * 60


class DashboardSessions:
    def __init__(self):
        self.sessions = {}
        self.lock = Lock()

    def issue(self, identity):
        token = token_urlsafe(32)
        now = monotonic()
        with self.lock:
            for expired in [key for key, (_, end) in self.sessions.items() if end <= now]:
                self.sessions.pop(expired)
            self.sessions[token] = (identity, now + SESSION_LIFETIME)
        return token

    def read(self, token):
        with self.lock:
            value = self.sessions.get(token)
            if not value:
                return None
            identity, expiry = value
            if expiry <= monotonic():
                self.sessions.pop(token)
                return None
            return identity

    def revoke(self, token):
        with self.lock:
            self.sessions.pop(token, None)
