"""Consignes d'exploitation locales et journal du brief."""
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def service_health():
    mode = os.environ.get("ORION_MODE", "simulation")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    ollama = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    n8n = os.environ.get("ORION_N8N_URL", "http://127.0.0.1:5678").rstrip("/")

    def probe(service, url):
        try:
            with urlopen(url, timeout=2) as response:
                if service == "Ollama":
                    payload = json.loads(response.read(1048576))
                    names = {entry["name"] for entry in payload["models"]}
                    if model not in names and f"{model}:latest" not in names:
                        return {"state": "warning", "detail": f"Modèle {model} absent."}
        except HTTPError as error:
            return {"state": "error", "detail": f"HTTP {error.code}"}
        except (URLError, OSError, ValueError, TypeError, KeyError):
            return {"state": "error", "detail": "Service indisponible ou réponse invalide."}
        return {"state": "online", "detail": model if service == "Ollama" else "Service joignable"}

    with ThreadPoolExecutor(max_workers=2) as pool:
        ollama_health = pool.submit(probe, "Ollama", ollama + "/api/tags")
        n8n_health = pool.submit(probe, "n8n", n8n + "/healthz")
        return {"mode": mode, "services": {
            "FastAPI": {"state": "online", "detail": "API ORION"},
            "Ollama": ollama_health.result(), "n8n": n8n_health.result(),
        }}


class BriefJournal:
    def __init__(self, path):
        self.path = path
        with closing(sqlite3.connect(path, timeout=10)) as db, db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS wedding_brief_runs (
                    id INTEGER PRIMARY KEY, origin TEXT NOT NULL,
                    state TEXT NOT NULL, finished_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def record(self, origin, state):
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("INSERT INTO wedding_brief_runs (origin, state) VALUES (?, ?)", (origin, state))

    def latest(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute("""
                SELECT origin, state, finished_at FROM wedding_brief_runs ORDER BY id DESC LIMIT 15
            """)]
