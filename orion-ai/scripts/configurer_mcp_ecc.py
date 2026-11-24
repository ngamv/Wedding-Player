"""Déclare les serveurs ECC prêts et indique les prérequis des autres."""

import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import NamedTemporaryFile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
TOKENS = {
    "arcmira": "ARCMIRA_API_KEY", "memxus": "MEMXUS_API_KEY",
    "browser-use": "BROWSER_USE_API_KEY", "supabase": "SUPABASE_ACCESS_TOKEN",
}


def preparer(nom, original):
    data = {k: copy.deepcopy(v) for k, v in original.items() if k != "description"}
    variables = []
    for key, value in data.get("env", {}).items():
        if value.startswith("YOUR_"):
            variables.append(key)
            data["env"][key] = "${" + key + "}"
    if nom in TOKENS:
        key = TOKENS[nom]
        variables.append(key)
        ref = "${" + key + "}"
        if nom == "browser-use":
            data["headers"]["x-browser-use-api-key"] = ref
        elif nom == "supabase":
            variables.append("SUPABASE_PROJECT_REF")
            data["env"] = {"SUPABASE_ACCESS_TOKEN": ref}
            data["args"] += ["--read-only", "--project-ref", "${SUPABASE_PROJECT_REF}"]
        else:
            data["headers"]["Authorization"] = "Bearer " + ref
    missing = [key for key in variables if not os.environ.get(key)]
    if missing:
        return None, "Variables : " + ", ".join(missing)
    if nom == "ito-compute":
        path = os.environ.get("ECC_ITO_MCP_PATH")
        if not path or not Path(path).is_file():
            return None, "Indiquer le runtime via ECC_ITO_MCP_PATH."
        data["args"] = [str(Path(path).resolve())]
    if nom == "evalview" and not shutil.which("evalview"):
        return None, "Installer le runtime EvalView."
    if nom == "devfleet":
        try:
            with urlopen("http://127.0.0.1:18801/mcp", timeout=1):
                pass
        except OSError as error:
            # Une réponse HTTP, même 405 sur GET, atteste que le port répond.
            if not getattr(error, "code", None):
                return None, "Démarrer DevFleet sur le port 18801."
    if nom == "playwright":
        browser = next((shutil.which(x) for x in ("google-chrome", "chromium", "chromium-browser") if shutil.which(x)), None)
        if browser:
            data["args"] = ["-y", "@playwright/mcp", "--executable-path", browser]
        elif os.name != "nt":
            return None, "Installer Chrome ou Chromium."
    if nom == "filesystem":
        dossier = ROOT / "mcp-partage"
        dossier.mkdir(exist_ok=True)
        data["args"][-1] = str(dossier)
    if nom == "memory":
        dossier = ROOT / "memory"
        dossier.mkdir(exist_ok=True)
        data["env"] = {"MEMORY_FILE_PATH": str(dossier / "ecc-memory.jsonl")}
    if nom == "sequential-thinking":
        data["args"][-1] = "@modelcontextprotocol/server-sequential-thinking@2.2.0"
    command = data.get("command")
    if command:
        if command == "python3":
            command = "python"
            data["command"] = command
        if not shutil.which(command):
            return None, f"Installer la commande {command}."
        if os.name == "nt" and command == "npx":
            data["command"] = "cmd"
            data["args"] = ["/d", "/c", "npx", *data["args"]]
    return data, "Déclaré, connexion à vérifier dans Claude Code."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("noms", nargs="*")
    parser.add_argument("--rapport", type=Path)
    args = parser.parse_args()
    fichier = ROOT / ".mcp.json"
    config = json.loads(fichier.read_text(encoding="utf-8"))
    if os.name == "nt":
        if "orion-wedding" in config["mcpServers"]:
            config["mcpServers"]["orion-wedding"]["command"] = sys.executable
        ruflo = config["mcpServers"].get("ruflo")
        if ruflo and ruflo["command"] == "npx":
            ruflo["command"] = "cmd"
            ruflo["args"] = ["/d", "/c", "npx", *ruflo["args"]]
    catalogue = json.loads((ROOT / "config/ecc-mcp.catalogue.json").read_text(encoding="utf-8"))["mcpServers"]
    rapport = {}
    for nom in args.noms or catalogue:
        if nom not in catalogue:
            parser.error(f"Profil inconnu : {nom}")
        data, statut = preparer(nom, catalogue[nom])
        key = "ecc-" + nom
        if data is not None:
            config["mcpServers"][key] = data
        rapport[nom] = {"declare": key in config["mcpServers"], "detail": statut}
        print(f"{nom}: {statut}")
    temporaire = None
    try:
        with NamedTemporaryFile(dir=ROOT, delete=False, mode="w", encoding="utf-8") as f:
            temporaire = Path(f.name)
            json.dump(config, f, ensure_ascii=False, indent=2)
        temporaire.replace(fichier)
    finally:
        if temporaire:
            temporaire.unlink(missing_ok=True)
    if args.rapport:
        args.rapport.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
