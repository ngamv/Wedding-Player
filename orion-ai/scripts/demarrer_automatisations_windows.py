"""Prépare et lance ORION, Ollama et n8n sur un PC Windows."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import urlopen

from scripts.orion_n8n import connect_workflow

ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3:0.6b"


def appel(url):
    try:
        with urlopen(url, timeout=1) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def attendre(url, label, seconds=45):
    for _ in range(seconds):
        result = appel(url)
        if result is not None:
            return result
        time.sleep(1)
    raise RuntimeError(f"{label} ne répond pas : {url}")


def run(args, **options):
    return subprocess.run(args, check=True, **options)


def console(args, env=None):
    return subprocess.Popen(
        args, cwd=ROOT, env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )


def planifier():
    env = {
        **os.environ, "ORION_PROJECT_DIR": str(ROOT), "ORION_PYTHON": sys.executable,
        "ORION_REPORT": str(ROOT / "memory" / "wedding-rappels.json"),
    }
    ps = """
$ErrorActionPreference = 'Stop'
$nom = 'ORION Wedding - Rappels'
if (-not (Get-ScheduledTask -TaskName $nom -ErrorAction SilentlyContinue)) {
    $argsRapport = '-m backend.wedding_digest --jours 7 --sortie "' + $env:ORION_REPORT + '"'
    $action = New-ScheduledTaskAction -Execute $env:ORION_PYTHON -WorkingDirectory $env:ORION_PROJECT_DIR -Argument $argsRapport
    $trigger = New-ScheduledTaskTrigger -Daily -At '09:00'
    $principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive
    Register-ScheduledTask -TaskName $nom -Action $action -Trigger $trigger -Principal $principal | Out-Null
}
"""
    run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], env=env)
    print(f"Rapport quotidien Windows : {env['ORION_REPORT']}")


def main():
    if os.name != "nt":
        raise RuntimeError("Ce lanceur cible Windows.")
    node = shutil.which("node.exe")
    npm = shutil.which("npm.cmd")
    ollama = shutil.which("ollama.exe")
    if not node or not npm or int(run([node, "-p", "process.versions.node.split('.')[0]"],
                                      capture_output=True, text=True).stdout.strip()) < 24:
        raise RuntimeError("Installez Node.js 24 LTS, puis rouvrez ce lanceur.")
    if not ollama:
        raise RuntimeError("Installez Ollama pour Windows, puis rouvrez ce lanceur.")
    ollama_url = "http://127.0.0.1:11434/api/version"
    if appel(ollama_url) is None:
        console([ollama, "serve"])
        attendre(ollama_url, "Ollama")
    run([ollama, "pull", MODEL], cwd=ROOT)

    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=ROOT)
    run([sys.executable, "scripts/configurer_mcp_ecc.py"], cwd=ROOT)
    env = {**os.environ, "ORION_MODE": "ollama", "OLLAMA_MODEL": MODEL}
    public = "http://127.0.0.1:8000/api/dashboard/status"
    status = appel(public)
    if status is None:
        console([sys.executable, "lancer_orion.py"], env)
        status = attendre(public, "ORION")
    if status.get("mode") != "ollama":
        raise RuntimeError("Fermez l’ancien serveur ORION sur le port 8000, puis relancez ce fichier.")

    root_n8n = Path(os.environ["LOCALAPPDATA"]) / "ORION-n8n"
    runtime = root_n8n / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    exe = runtime / "node_modules" / "n8n" / "bin" / "n8n"
    if not exe.is_file():
        run(["cmd.exe", "/d", "/c", "npm.cmd install --no-audit --no-fund n8n@2.48.8"], cwd=runtime)
    n8n_env = {
        **os.environ, "N8N_USER_FOLDER": str(root_n8n), "N8N_LISTEN_ADDRESS": "127.0.0.1",
        "N8N_HOST": "localhost", "N8N_PORT": "5678", "N8N_SECURE_COOKIE": "false",
        "N8N_DIAGNOSTICS_ENABLED": "false", "GENERIC_TIMEZONE": "Europe/Paris", "TZ": "Europe/Paris",
    }
    ready = "http://127.0.0.1:5678/healthz/readiness"
    if appel("http://127.0.0.1:5678/healthz") is not None:
        raise RuntimeError("n8n tourne déjà sur le port 5678. Fermez cette instance puis relancez ce fichier.")
    n8n = [node, str(exe)]
    connect_workflow(n8n, n8n_env)
    console([*n8n, "start"], n8n_env)
    attendre(ready, "n8n", seconds=90)
    planifier()
    print("ORION Wedding : http://127.0.0.1:8000/dashboard/#wedding")
    print("n8n : http://127.0.0.1:5678")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError) as error:
        print(f"Installation interrompue : {error}", file=sys.stderr)
        raise SystemExit(1)
