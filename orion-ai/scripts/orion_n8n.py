"""Raccorde l’automatisation Wedding à un n8n local arrêté."""
import argparse
import json
import os
import secrets
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

from core.memory import Memory
from core.n8n_access import USERNAME, configure
from scripts.orion_backup import ROOT, configured_databases

WORKFLOW_ID = "OrionWedding09h1"
CREDENTIAL_ID = "OrionWeddingReport1"
CREDENTIAL_NAME = "ORION · Rapport Wedding"
WORKFLOW = ROOT / "automations" / "n8n-wedding-quotidien.json"


def bind_workflow(workflow, base, template):
    names = ("Lire le rapport ORION", "Enregistrer le brief quotidien")
    prototype = {node["name"]: node for node in template["nodes"]}
    for name in names:
        node = next((node for node in workflow["nodes"] if node["name"] == name), None)
        if node is None:
            node = prototype[name]
            workflow["nodes"].append(node)
        if node["type"] != "n8n-nodes-base.httpRequest":
            raise ValueError(f"Le nœud « {name} » a été remplacé. Raccordement interrompu.")
        # Bind credentials exclusively to the project’s known local endpoints.
        endpoint = urlsplit(prototype[name]["parameters"]["url"])
        parameters = dict(prototype[name]["parameters"])
        parameters.update(url=base + endpoint.path + "?" + endpoint.query, authentication="genericCredentialType",
                          genericAuthType="httpBasicAuth")
        node["parameters"] = parameters
        node["credentials"] = {"httpBasicAuth": {"id": CREDENTIAL_ID, "name": CREDENTIAL_NAME}}
    connections = workflow["connections"].setdefault(names[0], {}).setdefault("main", [[]])
    if not connections:
        connections.append([])
    if not any(link["node"] == names[1] for link in connections[0]):
        connections[0].append({"node":names[1], "type":"main", "index":0})
    return workflow


def connect_workflow(n8n, env, port=8000):
    template = json.loads(WORKFLOW.read_text(encoding="utf-8"))

    def cli(*args, success=None):
        output = subprocess.run([*n8n, *args], env=env, cwd=ROOT, check=True,
                                capture_output=True, text=True, encoding="utf-8")
        if success and success not in output.stdout + output.stderr:
            raise RuntimeError("n8n n’a pas confirmé l’opération. Vérifiez le compte propriétaire et ses droits.")
        return output.stdout

    ids = cli("list:workflow", "--onlyId").splitlines()
    with TemporaryDirectory(prefix="orion-n8n-") as directory:
        path = Path(directory)
        workflow_path = path / "workflow.json"
        if WORKFLOW_ID in {line.strip() for line in ids}:
            cli("export:workflow", "--id=" + WORKFLOW_ID, "--output=" + str(workflow_path))
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))[0]
        else:
            workflow = template
        updated = bind_workflow(workflow, f"http://127.0.0.1:{port}", template)
        workflow_path.write_text(json.dumps([updated]), encoding="utf-8")
        token = secrets.token_urlsafe(32)
        credential_path = path / "credential.json"
        credential_path.write_text(json.dumps([{
            "id": CREDENTIAL_ID, "type": "httpBasicAuth", "name": CREDENTIAL_NAME,
            "data": {"user": USERNAME, "password": token},
        }]), encoding="utf-8")
        cli("import:credentials", "--input=" + str(credential_path), success="Successfully imported 1 credential")
        cli("import:workflow", "--input=" + str(workflow_path), success="Successfully imported 1 workflow")
        database, _ = configured_databases()
        Memory(database)
        configure(database, token)
        cli("publish:workflow", "--id=" + WORKFLOW_ID, success="Publishing workflow with ID:")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default="node")
    parser.add_argument("--n8n", required=True, type=Path, help="Chemin du fichier n8n/bin/n8n.")
    parser.add_argument("--folder", required=True, type=Path, help="Dossier N8N_USER_FOLDER déjà configuré.")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Le port doit être compris entre 1 et 65535.")
    connect_workflow([args.node, str(args.n8n.resolve())],
                     {**os.environ, "N8N_USER_FOLDER":str(args.folder.resolve())}, args.port)
    print("Workflow Wedding raccordé avec un identifiant dédié.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(f"Raccordement interrompu : {error}") from None
