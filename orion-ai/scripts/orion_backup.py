"""Sauvegarde et restauration des deux bases SQLite ORION dans un dossier neuf."""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from zoneinfo import ZoneInfo
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("orion.sqlite3", "wedding.sqlite3")
MANIFEST = "manifest.json"
TABLES = {
    "orion.sqlite3": {"workflows", "projects", "project_tasks", "inbox_entries", "managed_sites",
                      "business_items", "ceo_briefs"},
    "wedding.sqlite3": {"wedding_plans", "wedding_reminders", "wedding_records",
                        "wedding_notes", "wedding_briefs"},
}


def configured_databases():
    orion = Path(os.environ.get("ORION_DB", ROOT / "memory" / NAMES[0]))
    wedding = Path(os.environ.get("ORION_WEDDING_DB", orion.with_name(NAMES[1])))
    return orion, wedding


def check_sqlite(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError(f"Base SQLite invalide : {path.name}")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        expected = TABLES[path.name]
        opposite = TABLES[NAMES[1] if path.name == NAMES[0] else NAMES[0]]
        if tables & opposite and not tables & expected:
            raise ValueError(f"Type de base inattendu : {path.name}")
        return {table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in sorted(tables & expected)}


def fingerprint(path):
    with path.open("rb") as stream:
        return {"sha256": hashlib.file_digest(stream, "sha256").hexdigest(), "bytes": path.stat().st_size}


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
            bundle.writestr(MANIFEST, json.dumps({
                "version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                "files": {name: fingerprint(directory / name) for name in NAMES},
            }, indent=2))
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(descriptor, "wb") as output:
            try:
                with archive.open("rb") as source:
                    shutil.copyfileobj(source, output)
            except BaseException:
                output.close()
                destination.unlink(missing_ok=True)
                raise


def read_manifest(bundle):
    if bundle.getinfo(MANIFEST).file_size > 16384:
        raise ValueError("Manifeste de sauvegarde trop volumineux.")
    info = json.loads(bundle.read(MANIFEST))
    if not isinstance(info, dict) or info.get("version") != 1:
        raise ValueError("Version du manifeste de sauvegarde inconnue.")
    if not isinstance(info.get("created_at"), str) or not isinstance(info.get("files"), dict):
        raise ValueError("Manifeste de sauvegarde incomplet.")
    created = datetime.fromisoformat(info["created_at"])
    if created.tzinfo is None or set(info["files"]) != set(NAMES):
        raise ValueError("Manifeste de sauvegarde incomplet.")
    return info


@contextmanager
def verified_snapshot(archive):
    with TemporaryDirectory() as tmp, ZipFile(archive) as bundle:
        names = sorted(bundle.namelist())
        if names not in (sorted(NAMES), sorted((*NAMES, MANIFEST))):
            raise ValueError("L’archive doit contenir les deux bases et éventuellement un manifeste.")
        manifest = read_manifest(bundle) if MANIFEST in names else None
        directory = Path(tmp)
        items = {}
        for name in NAMES:
            bundle.extract(name, directory)
            path = directory / name
            signature = fingerprint(path)
            if manifest and manifest["files"][name] != signature:
                raise ValueError(f"Empreinte ou taille différente du manifeste : {name}")
            items[name] = {**signature, "tables": check_sqlite(path)}
        yield directory, {
            "created_at": manifest["created_at"] if manifest else None,
            "manifest_verified": manifest is not None,
            "files": items,
        }


def verify(archive):
    with verified_snapshot(archive) as (_, details):
        return details


def copy_snapshot(directory, destination):
    destination.mkdir(mode=0o700)
    try:
        for name in NAMES:
            shutil.copyfile(directory / name, destination / name)
    except BaseException:
        shutil.rmtree(destination)
        raise


def restore(archive, destination):
    with verified_snapshot(archive) as (directory, _):
        copy_snapshot(directory, destination)


def backup_directory():
    return Path(os.environ.get("ORION_BACKUP_DIR", ROOT / "backups"))


def backup_status():
    try:
        status = json.loads((backup_directory() / "status.json").read_text(encoding="utf-8"))
        snapshot = status.get("verified")
        if snapshot:
            name = snapshot["archive"]
            if Path(name).name != name or not (backup_directory() / name).is_file():
                return {**status, "state": "missing"}
        return status
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return None


def write_status(directory, value):
    with NamedTemporaryFile(dir=directory, delete=False, mode="w", encoding="utf-8") as stream:
        path = Path(stream.name)
        try:
            json.dump(value, stream)
        except BaseException:
            stream.close()
            path.unlink(missing_ok=True)
            raise
    try:
        path.replace(directory / "status.json")
    finally:
        path.unlink(missing_ok=True)


def daily_backup():
    directory = backup_directory()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    paris_now = datetime.now(ZoneInfo("Europe/Paris"))
    label = paris_now.strftime("%Y-%m-%d_%H%M%S_%f")
    destination = directory / f"orion-{label}.zip"
    try:
        with TemporaryDirectory(dir=directory, prefix=".orion-backup-") as scratch:
            staged = Path(scratch) / "snapshot.zip"
            backup(staged)
            integrity = verify(staged)
            staged.replace(destination)
    except (OSError, ValueError, sqlite3.Error, BadZipFile):
        previous = backup_status()
        verified = previous.get("verified") if previous and previous.get("state") != "missing" else None
        write_status(directory, {"state": "failed", "attempted_at": datetime.now(timezone.utc).isoformat(),
                                 "verified": verified})
        raise
    now = datetime.now(timezone.utc).isoformat()
    write_status(directory, {"state": "verified", "attempted_at": now,
                             "verified": {"at": now, "archive": destination.name,
                                          "manifest_verified": integrity["manifest_verified"]}})
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    snapshot = sub.add_parser("backup")
    snapshot.add_argument("archive", type=Path)
    recover = sub.add_parser("restore")
    recover.add_argument("archive", type=Path)
    recover.add_argument("directory", type=Path)
    inspection = sub.add_parser("verify")
    inspection.add_argument("archive", type=Path)
    detail = sub.add_parser("inspect")
    detail.add_argument("archive", type=Path)
    sub.add_parser("daily")
    args = parser.parse_args()
    try:
        if args.command == "backup":
            backup(args.archive)
            print(f"Sauvegarde créée : {args.archive}")
        elif args.command == "restore":
            restore(args.archive, args.directory)
            print(f"Bases restaurées : {args.directory}")
        elif args.command == "verify":
            verify(args.archive)
            print(f"Archive vérifiée : {args.archive}")
        elif args.command == "inspect":
            print(json.dumps(verify(args.archive), indent=2, ensure_ascii=False))
        else:
            print(f"Sauvegarde datée vérifiée : {daily_backup()}")
    except (OSError, ValueError, sqlite3.Error, BadZipFile) as error:
        parser.exit(1, f"Opération interrompue : {error}\n")


if __name__ == "__main__":
    main()
