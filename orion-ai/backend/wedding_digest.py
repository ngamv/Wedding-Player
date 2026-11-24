"""Produit les rappels dans le terminal ou un fichier JSON local."""

import argparse
import json
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from backend.main import brief_journal, wedding_dossier, wedding_store, wedding_today


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jours", type=int, default=7)
    parser.add_argument("--date", type=date.fromisoformat, default=wedding_today())
    parser.add_argument("--sortie", type=Path)
    args = parser.parse_args()
    if not 0 <= args.jours <= 90:
        parser.error("--jours doit être compris entre 0 et 90.")
    journal = brief_journal()
    try:
        generate(args)
    except Exception:
        journal.record("scheduler", "failed")
        raise
    journal.record("scheduler", "completed")


def generate(args):
    store = wedding_store()
    rapport = store.digest_all(args.date, args.jours)
    dossier = wedding_dossier()
    overview = dossier.overview(args.date, args.jours, prepare=True)
    texte = json.dumps(rapport, ensure_ascii=False, indent=2) + "\n"
    if args.sortie:
        args.sortie.parent.mkdir(parents=True, exist_ok=True)
        temporaire = None
        try:
            with NamedTemporaryFile(dir=args.sortie.parent, delete=False, mode="w", encoding="utf-8") as f:
                temporaire = Path(f.name)
                f.write(texte)
            temporaire.replace(args.sortie)
        finally:
            if temporaire is not None:
                temporaire.unlink(missing_ok=True)
    else:
        print(texte, end="")
    dossier.save_brief(overview)


if __name__ == "__main__":
    main()
