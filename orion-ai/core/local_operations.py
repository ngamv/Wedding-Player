"""Consignes d'exploitation locales et journal du brief."""
import json
import os
import shutil
import sqlite3
import subprocess
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener, urlopen

from .wedding_mail import smtp_config


def service_health(port=None):
    mode = os.environ.get("ORION_MODE", "simulation")
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
    ollama = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    n8n = os.environ.get("ORION_N8N_URL", "http://127.0.0.1:5678").rstrip("/")

    def probe(service, url):
        try:
            open_url = build_opener(ProxyHandler({})).open if service == "FastAPI" else urlopen
            with open_url(url, timeout=2) as response:
                if service == "FastAPI":
                    payload = json.loads(response.read(1048576))
                    if payload.get("status") != "online" or payload.get("environment") != "FastAPI local":
                        return {"state": "error", "detail": "Le port ne répond pas comme une API ORION."}
                if service == "Ollama":
                    payload = json.loads(response.read(1048576))
                    names = {entry["name"] for entry in payload["models"]}
                    if model not in names and f"{model}:latest" not in names:
                        return {"state": "warning", "detail": f"Modèle {model} absent."}
        except HTTPError as error:
            return {"state": "error", "detail": f"HTTP {error.code}"}
        except (URLError, OSError, ValueError, TypeError, KeyError, AttributeError):
            return {"state": "error", "detail": "Service indisponible ou réponse invalide."}
        return {"state": "online", "detail": model if service == "Ollama" else "Service joignable"}

    with ThreadPoolExecutor(max_workers=3) as pool:
        ollama_health = pool.submit(probe, "Ollama", ollama + "/api/tags")
        n8n_health = pool.submit(probe, "n8n", n8n + "/healthz")
        fastapi_health = (pool.submit(probe, "FastAPI", f"http://127.0.0.1:{port}/api/dashboard/status").result()
                          if port is not None else {"state": "online", "detail": "API ORION"})
        return {"mode": mode, "services": {
            "FastAPI": fastapi_health,
            "Ollama": ollama_health.result(), "n8n": n8n_health.result(),
        }}


def capability_report(health):
    def state(label, detail):
        return {"state": label, "detail": detail}

    def tools(*names):
        return [name for name in names if shutil.which(name) is None]

    def missing(names):
        return "Exécutables manquants : " + ", ".join(names)

    absent = tools("pdftotext")
    pdf = state("action", missing(absent)) if absent else state("ready", "pdftotext est disponible.")

    ocr_missing = tools("tesseract")
    languages = os.environ.get("ORION_OCR_LANG", "fra+eng").split("+")
    if ocr_missing:
        ocr = state("action", missing(ocr_missing))
    else:
        try:
            result = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True,
                                    errors="replace", check=True, timeout=2)
            unavailable = sorted(set(languages) - set(result.stdout.splitlines()))
            ocr = (state("action", "Langues OCR manquantes : " + ", ".join(unavailable)) if unavailable
                   else state("ready", "Langues disponibles : " + ", ".join(languages)))
        except (OSError, subprocess.SubprocessError):
            ocr = state("action", "Impossible de vérifier les langues Tesseract.")
    scan_missing = tools("pdftotext", "pdftoppm")
    scanned = state("action", missing(scan_missing)) if scan_missing else ocr

    audio_missing = tools("ffmpeg", "whisper-cli")
    model = os.environ.get("ORION_WHISPER_MODEL")
    if audio_missing:
        audio = state("action", missing(audio_missing))
    elif not model or not Path(model).is_file() or not os.access(model, os.R_OK):
        audio = state("action", "Indiquez un modèle Whisper local lisible via ORION_WHISPER_MODEL.")
    else:
        audio = state("ready", "Exécutables et fichier modèle détectés. Lancez un essai de transcription.")

    if health["mode"] != "ollama":
        ai = state("action", "ORION fonctionne en simulation. Activez le mode Ollama pour générer des réponses.")
    elif health["services"]["Ollama"]["state"] != "online":
        ai = state("action", health["services"]["Ollama"]["detail"])
    else:
        ai = state("ready", "Service joignable et modèle installé.")
    automation = (state("ready", "Service n8n joignable. Vérifiez le workflow publié dans n8n.")
                  if health["services"]["n8n"]["state"] == "online"
                  else state("action", "Démarrez n8n et actualisez le diagnostic."))
    mail = (state("check", "Configuration SMTP détectée. L’envoi réel reste à tester.") if smtp_config()
            else state("action", "Configurez le serveur SMTP, l’expéditeur et les identifiants requis."))
    if os.environ.get("ORION_RECOVERY") == "1":
        mail = state("disabled", "Envoi désactivé dans la copie de restauration.")

    return {"Réponses IA": ai, "Automatisations n8n": automation, "PDF texte": pdf,
            "JPEG OCR": ocr, "PDF scanné": scanned, "Transcription audio": audio,
            "Relances e-mail": mail}


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
