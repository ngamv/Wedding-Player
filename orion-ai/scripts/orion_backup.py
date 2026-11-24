"""Sauvegarde et restauration des deux bases SQLite ORION dans un dossier neuf."""
import argparse
import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("orion.sqlite3", "wedding.sqlite3")


def configured_databases():
    orion = Path(os.environ.get("ORION_DB", ROOT / "memory" / NAMES[0]))
    wedding = Path(os.environ.get("ORION_WEDDING_DB", orion.with_name(NAMES[1])))
    return orion, wedding


def check_sqlite(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError(f"Base SQLite invalide : {path.name}")


def backup(destination):
    with TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for source, name in zip(configured_databases(), NAMES, strict=True):
            target = directory / name
            with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as live:
                with closing(sqlite3.connect(target)) as copy:
                    live.backup(copy)
            check_sqlite(target)
        archive = directory / "snapshot.zip"
        with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
            for name in NAMES:
                bundle.write(directory / name, name)
        with destination.open("xb") as output:
            try:
                with archive.open("rb") as source:
                    shutil.copyfileobj(source, output)
            except BaseException:
                output.close()
                destination.unlink(missing_ok=True)
                raise


def restore(archive, destination):
    with TemporaryDirectory() as tmp, ZipFile(archive) as bundle:
        if sorted(bundle.namelist()) != sorted(NAMES):
            raise ValueError("L’archive doit contenir exactement les deux bases attendues.")
        for name in NAMES:
            bundle.extract(name, tmp)
            check_sqlite(Path(tmp) / name)
        destination.mkdir()
        try:
            for name in NAMES:
                shutil.copyfile(Path(tmp) / name, destination / name)
        except BaseException:
            shutil.rmtree(destination)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    snapshot = sub.add_parser("backup")
    snapshot.add_argument("archive", type=Path)
    recover = sub.add_parser("restore")
    recover.add_argument("archive", type=Path)
    recover.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "backup":
            backup(args.archive)
            print(f"Sauvegarde créée : {args.archive}")
        else:
            restore(args.archive, args.directory)
            print(f"Bases restaurées : {args.directory}")
    except (OSError, ValueError, sqlite3.Error, BadZipFile) as error:
        parser.exit(1, f"Opération interrompue : {error}\n")


if __name__ == "__main__":
    main()
