# ORION sur macOS

Installez Python 3.12 depuis python.org ou avec Homebrew (`brew install python@3.12`). Après extraction du ZIP, ouvrez Terminal et placez-vous dans le dossier `orion-ai` qui contient `lancer_macos.sh`.

```bash
bash lancer_macos.sh
```

Le script crée un environnement Python dans `.venv`, installe les dépendances et démarre ORION. Gardez le terminal ouvert, puis ouvrez le tableau de bord sur http://127.0.0.1:8000/dashboard/#workflows. Pour Wedding, ouvrez http://127.0.0.1:8000/dashboard/#wedding. Si le port 8000 est occupé, lancez `bash lancer_macos.sh --port 8020`.

## Ollama et MCP

ORION démarre en simulation par défaut. Pour générer avec Qwen3, installez et ouvrez Ollama, lancez `ollama pull qwen3:8b`, puis démarrez ORION avec la commande suivante.

```bash
ORION_MODE=ollama OLLAMA_MODEL=qwen3:8b bash lancer_macos.sh
```

Pour le serveur MCP Wedding, utilisez le dossier ORION comme répertoire de travail, l’interpréteur `.venv/bin/python` et les arguments `-m backend.wedding_mcp`. Le serveur utilise stdio.
