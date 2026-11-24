"""Prépare l’environnement Python d’ORION et transmet les options du lanceur."""
import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info < (3, 12):
        print("Python 3.12 ou plus récent est requis.", file=sys.stderr)
        return 1
    environment = ROOT / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        print("Création de l’environnement Python local…", flush=True)
        venv.create(environment, with_pip=True)
    requirements = ROOT / "requirements.txt"
    checksum = hashlib.sha256(requirements.read_bytes()).hexdigest()
    stamp = environment / "orion-requirements.sha256"
    if not stamp.is_file() or stamp.read_text(encoding="ascii") != checksum:
        print("Installation des dépendances ORION…", flush=True)
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(requirements)],
                       cwd=ROOT, check=True)
        stamp.write_text(checksum, encoding="ascii")
    return subprocess.call([str(python), str(ROOT / "lancer_orion.py"), *sys.argv[1:]], cwd=ROOT)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.SubprocessError) as error:
        print(f"Impossible de préparer ORION : {error}", file=sys.stderr)
        raise SystemExit(1) from None
