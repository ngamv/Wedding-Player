"""Lance ou diagnostique le tableau de bord ORION local."""
import argparse
import importlib
import os
import socket
import sqlite3
import subprocess
import sys
import time
import webbrowser
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryFile
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

from scripts.orion_backup import configured_databases

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"


def database_problem(path):
    try:
        if path.exists():
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
                if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    return "contrôle SQLite en échec"
            if not os.access(path, os.W_OK):
                return "fichier SQLite en lecture seule"
        parent = path.parent
        while not parent.exists():
            parent = parent.parent
        with TemporaryFile(dir=parent):
            pass
    except (sqlite3.Error, OSError):
        return "base inaccessible ou emplacement non inscriptible"
    return None


def diagnostics(port):
    issues = []
    if sys.version_info < (3, 12):
        issues.append("Python 3.12 ou plus récent est requis.")
    for name in ("fastapi", "uvicorn", "yaml", "python_multipart"):
        try:
            importlib.import_module(name)
        except ImportError:
            issues.append(f"Dépendance manquante ou incompatible : {name}.")
    for path in configured_databases():
        failure = database_problem(path)
        if failure:
            issues.append(f"{path} : {failure}.")
    if not (ROOT / "frontend/dashboard/index.html").is_file():
        issues.append("Tableau de bord introuvable. Extrayez toute l’archive ORION.")
    try:
        with socket.socket() as listener:
            listener.bind((HOST, port))
    except OSError:
        issues.append(f"Le port {port} ne peut pas être utilisé. Vérifiez le serveur existant ou choisissez --port 8001.")
    return issues


def launch(port, open_browser):
    address = f"http://{HOST}:{port}"
    dashboard = address + "/dashboard/"
    with subprocess.Popen([
        sys.executable, "-m", "uvicorn", "backend.main:app",
        "--host", HOST, "--port", str(port),
    ], cwd=ROOT) as server:
        try:
            deadline = time.monotonic() + 25
            client = build_opener(ProxyHandler({}))
            while time.monotonic() < deadline and server.poll() is None:
                try:
                    with client.open(dashboard, timeout=0.5) as response:
                        if response.status == 200:
                            print(f"ORION est prêt : {dashboard}", flush=True)
                            if open_browser:
                                webbrowser.open(dashboard)
                            return server.wait()
                except (URLError, OSError):
                    time.sleep(0.2)
            print("Le tableau de bord n’a pas répondu. Consultez les messages du serveur ci-dessus.",
                  file=sys.stderr, flush=True)
            if server.poll() is None:
                server.terminate()
            return server.wait() or 1
        except KeyboardInterrupt:
            if server.poll() is None:
                try:
                    return server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.terminate()
            return server.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--check", action="store_true", help="Vérifie l’installation sans démarrer le serveur.")
    parser.add_argument("--open", action="store_true", help="Ouvre le tableau de bord quand le serveur répond.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Le port doit être compris entre 1 et 65535.")
    os.chdir(ROOT)
    issues = diagnostics(args.port)
    if issues:
        for issue in issues:
            print(issue, file=sys.stderr)
        return 1
    if args.check:
        print(f"Diagnostic réussi. Python, dépendances, bases SQLite et port {args.port} disponibles.")
        return 0
    return launch(args.port, args.open)


if __name__ == "__main__":
    raise SystemExit(main())
