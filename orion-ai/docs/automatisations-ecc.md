# ORION · Automatisations locales Windows

Pré-requis : Python 3.12, Node.js 24 et Ollama pour Windows. Après extraction, double-cliquez sur `Activer-ORION.cmd`. Le lanceur installe npm en mode utilisateur et ne dépend pas de Docker Desktop. Il vérifie les services, démarre Ollama et télécharge Qwen3 0.6B, installe les dépendances ORION, configure les MCP prêts, démarre le tableau de bord, puis importe et publie le workflow n8n. Il crée aussi le rappel quotidien à 09 h dans le Planificateur Windows si aucun rappel ORION Wedding du même nom n’existe. Un rappel existant est conservé.

Après lancement, gardez les consoles ORION et n8n ouvertes. Au premier accès à n8n, terminez la création du compte local dans l’éditeur à http://127.0.0.1:5678. Le workflow `Rapport Wedding ORION` interroge http://127.0.0.1:8000/api/wedding/daily-report à 09 h, heure de Paris. Il stocke le résultat dans l’historique n8n. Le rappel Windows écrit également `memory/wedding-rappels.json` à 09 h, heure du PC, sans dépendre du serveur web. Le rapport contient les noms des dossiers et leurs échéances et reste en local.

Pour retrouver des dossiers existants, lancez le fichier depuis votre dossier ORION mis à jour ou réutilisez la même base SQLite via `ORION_WEDDING_DB`. Le ZIP contient des fichiers applicatifs. Faites une copie de votre dossier ORION avant une mise à jour sur place.

## Serveurs MCP ECC

```powershell
py -3.12 scripts\configurer_mcp_ecc.py
```

La commande configure les profils dont les prérequis sont présents. La liste complète se trouve dans `config/ecc-mcp.catalogue.json`. Lancez la commande depuis la même session qui démarrera Claude Code si certains profils utilisent des variables d’environnement. Les jetons restent dans l’environnement. Après redémarrage de Claude Code, `/mcp` permet d’autoriser les connexions OAuth et de constater les erreurs éventuelles. Filesystem est limité au dossier `mcp-partage` créé dans ORION.

Un profil déjà déclaré peut encore échouer si son service réclame un compte, un abonnement ou une autorisation OAuth. Le rapport de configuration n’implique pas une connexion réussie.
