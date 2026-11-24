"""Ouvre une sauvegarde ORION dans une instance de contrôle séparée."""
import argparse
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from tempfile import mkdtemp
from zipfile import BadZipFile

from scripts.orion_backup import NAMES, ROOT, backup_directory, copy_snapshot, verified_snapshot


def preview(details):
    lines = [
        "Archive du " + (details["created_at"] or "jour inconnu"),
        "Empreintes SHA-256 vérifiées" if details["manifest_verified"] else "Ancienne archive · contrôle SQLite réussi",
    ]
    names = {"projects": "projets", "wedding_plans": "dossiers Wedding",
             "inbox_entries": "entrées Mémoire", "workflows": "workflows"}
    for label, database in details["files"].items():
        counters = [f"{count} {names[table]}" for table, count in database["tables"].items() if table in names]
        lines.append(label + " · " + (" · ".join(counters) if counters else f'{database["bytes"]} octets'))
    return "\n".join(lines)


def prepare(archive, destination, confirm):
    with verified_snapshot(archive) as (snapshot, details):
        if not confirm(preview(details)):
            return None
        destination.mkdir(mode=0o700, parents=True, exist_ok=True)
        instance = Path(mkdtemp(prefix="restauration-", dir=destination))
        data = instance / "data"
        try:
            copy_snapshot(snapshot, data)
        except BaseException:
            instance.rmdir()
            raise
    return data


def recovery_environment(data):
    result = dict(os.environ)
    for key in tuple(result):
        if key.startswith("ORION_SMTP_"):
            result.pop(key)
    result.update(
        ORION_RECOVERY="1",
        ORION_MODE="simulation",
        ORION_DB=str(data / NAMES[0]),
        ORION_WEDDING_DB=str(data / NAMES[1]),
        ORION_CHROMA=str(data / "orion.chroma"),
        ORION_IMPORT_DIR=str(data / "imports"),
        ORION_BACKUP_DIR=str(data / "backups"),
    )
    (data / "imports").mkdir(exist_ok=True)
    return result


def prepare_from_picker(destination):
    try:
        from tkinter import Tk, TclError, filedialog, messagebox
    except ImportError as error:
        raise ValueError("Sélecteur graphique indisponible. Passez le chemin du ZIP en argument.") from error
    try:
        window = Tk()
    except TclError as error:
        raise ValueError("Sélecteur graphique indisponible. Passez le chemin du ZIP en argument.") from error
    window.withdraw()
    try:
        default = backup_directory()
        archive = filedialog.askopenfilename(
            parent=window, title="Choisir une sauvegarde ORION",
            initialdir=str(default if default.is_dir() else ROOT),
            filetypes=[("Sauvegardes ZIP", "*.zip")],
        )
        if not archive:
            return None
        return prepare(Path(archive), destination, lambda message: messagebox.askyesno(
            "Ouvrir une copie de la sauvegarde",
            message + "\n\nCréer une copie séparée pour contrôler les données ?", parent=window,
        ))
    finally:
        window.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--prepare-only", action="store_true", help="Prépare la copie sans lancer le serveur.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Le port doit être compris entre 1 et 65535.")
    destination = Path(os.environ.get("ORION_RESTORE_DIR", ROOT / "restores")).resolve()
    try:
        if args.archive:
            def confirm(details):
                print(details)
                return args.prepare_only or input("Créer une copie séparée ? [o/N] ").strip().lower() == "o"
            data = prepare(args.archive, destination, confirm)
        else:
            data = prepare_from_picker(destination)
        if data is None:
            return 0
        print(f"Copie restaurée : {data}", flush=True)
        if args.prepare_only:
            return 0
        return subprocess.call([sys.executable, "-m", "scripts.orion_bootstrap",
                                "--port", str(args.port), "--open"], cwd=ROOT,
                               env=recovery_environment(data))
    except (OSError, ValueError, EOFError, sqlite3.Error, BadZipFile) as error:
        parser.exit(1, f"Restauration interrompue : {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
