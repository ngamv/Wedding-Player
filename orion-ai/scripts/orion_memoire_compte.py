"""Crée un compte local pour l'espace Mémoire."""
import argparse
import sqlite3
from getpass import getpass

from backend.main import inbox_accounts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    parser.add_argument("--role", choices=("admin", "member"), default="member")
    args = parser.parse_args()
    password = getpass("Mot de passe : ")
    if password != getpass("Confirmez le mot de passe : "):
        parser.exit(1, "Les mots de passe diffèrent.\n")
    try:
        inbox_accounts().add(args.username, password, args.role)
    except (ValueError, sqlite3.IntegrityError) as error:
        parser.exit(1, f"Compte non créé : {error}\n")
    print("Compte créé.")


if __name__ == "__main__":
    main()
