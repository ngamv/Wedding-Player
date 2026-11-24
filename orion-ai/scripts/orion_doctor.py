"""Indique les services et fonctions disponibles pour ORION."""
import argparse
import json

from core.local_operations import capability_report, service_health
from scripts.orion_backup import backup_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--json", action="store_true", help="Produit un rapport JSON.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Le port doit être compris entre 1 et 65535.")
    health = service_health(port=args.port)
    capabilities = capability_report(health)
    backup = backup_status()
    if args.json:
        print(json.dumps({**health, "capabilities": capabilities, "backup": backup}, ensure_ascii=False, indent=2))
    else:
        print(f'Mode ORION · {health["mode"]}')
        labels = {"online": "En ligne", "error": "Indisponible", "warning": "À vérifier",
                  "ready": "Disponible", "action": "À configurer", "check": "À tester", "disabled": "Désactivé"}
        for name, row in {**health["services"], **capabilities}.items():
            print(f'{name} · {labels[row["state"]]} · {row["detail"]}')
    return int(health["services"]["FastAPI"]["state"] != "online")


if __name__ == "__main__":
    raise SystemExit(main())
