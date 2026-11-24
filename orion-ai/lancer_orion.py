"""Lance le tableau de bord sur l’ordinateur où ce fichier est exécuté."""

import argparse
from pathlib import Path
import subprocess
import sys


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    port = parser.parse_args().port
    if not 1 <= port <= 65535:
        parser.error("Le port doit être compris entre 1 et 65535.")
    racine = Path(__file__).resolve().parent
    print(f"Une fois le serveur démarré, ouvrez http://127.0.0.1:{port}/dashboard/#workflows", flush=True)
    raise SystemExit(subprocess.call([
        sys.executable, "-m", "uvicorn", "backend.main:app",
        "--host", "127.0.0.1", "--port", str(port),
    ], cwd=racine))
