# ORION Wedding Planner

L’onglet Wedding Planner charge six modèles et préremplit la mission et sa séquence d’agents. Ajoutez votre brief puis lancez l’exécution sur le serveur local. Le site Vercel propose une simulation dans le navigateur. Les 20 sous-agents Wedding rejoignent les 80 profils ORION. Les six skills `/wedding-decouverte`, `/wedding-conception`, `/wedding-prestataires`, `/wedding-preparation`, `/wedding-jour-j` et `/wedding-cloture` sont disponibles dans Claude Code après ouverture du dossier du projet.

## MCP sur Windows

Depuis la racine du projet, installez les dépendances avec `py -3.12 -m pip install -r requirements.txt`. Le serveur MCP local utilise stdio. Dans un client MCP, utilisez la commande `py` et les arguments `-3.12 -m backend.wedding_mcp`, avec la racine du projet comme dossier de travail. Dans Claude Code, le fichier `.mcp.json` configure le serveur de projet. Adaptez sa commande à `py` avec l’argument initial `-3.12` si `python` ne pointe pas vers l’interpréteur où les dépendances sont installées.

- `wedding_planner` liste les modèles.
- `wedding_prepare` renvoie la mission et l’ordre des agents pour relecture.
- `wedding_run` exécute un modèle avec votre brief et enregistre le workflow dans SQLite.

La simulation est le mode par défaut. Pour générer avec Qwen3 sur Windows, démarrez Ollama, lancez `ollama pull qwen3:8b`, puis définissez `$env:ORION_MODE = 'ollama'` et `$env:OLLAMA_MODEL = 'qwen3:8b'` avant de démarrer ORION ou le client MCP depuis PowerShell.

Les workflows produisent des plans et brouillons à valider. Les connexions Telegram et WhatsApp ainsi que les envois, réservations, signatures et paiements demanderaient des intégrations distinctes.

## Guide des 100 tâches

Dans l’onglet Wedding Planner, créez un dossier et indiquez la date du mariage et les options. Le catalogue reprend les 100 tâches du guide daté du 15 novembre 2026, leurs échéances indicatives J−450 à J+60, priorités, responsables et 53 liens de dépendance. Les options « seulement si » et l’audition demandée sont désactivées par défaut. Par exemple, sans contrat de mariage, la signature est écartée ainsi que son lien vers le dépôt du dossier en mairie. Les détails juridiques et les conseils datés du guide restent à faire valider auprès de l’organisme concerné.

Les dossiers et l’avancement sont stockés dans `memory/wedding.sqlite3`, ou au chemin `ORION_WEDDING_DB`. Pour reprendre vos dossiers lors d’une mise à jour, réutilisez la même base. Les modèles de workflows produisent des livrables de travail. Le suivi des tâches se fait dans le dossier local et n’exécute aucun envoi, paiement ou réservation.

Deux nouveaux skills accompagnent le suivi : `/wedding-retroplanning` et `/wedding-revue-echeances`. Le serveur MCP ajoute les outils `wedding_list_plans`, `wedding_create_checklist`, `wedding_read_checklist`, `wedding_update_task` et `wedding_deadlines`.

## Rapport quotidien local

En PowerShell, depuis le projet avec ses dépendances installées :

```powershell
py -3.12 -m backend.wedding_digest --jours 7 --sortie .\memory\wedding-rappels.json
.\scripts\installer_rappel_wedding.ps1 -Heure '09:00'
```

La deuxième commande ajoute un rappel Windows quotidien à l’heure locale, exécuté quand l’utilisateur est connecté. Le rapport est un fichier JSON mis à jour pour tous les dossiers. Vous pouvez modifier l’horaire dans le Planificateur de tâches. Gardez le projet au même emplacement pour que la tâche puisse l’exécuter.

Sur macOS, après installation avec `lancer_macos.sh`, exécutez :

```bash
.venv/bin/python -m backend.wedding_digest --jours 7 --sortie memory/wedding-rappels.json
```

Pour la planification macOS, exécutez cette commande depuis le dossier ORION avec votre planificateur local. Aucun message externe n’est envoyé.

## Du prospect au bilan

Dans le tableau de bord local, ouvre **Wedding Planner** et crée ou sélectionne un dossier.
Au stade prospect, indique une date prévisionnelle. La modification de cette date recalcule les
échéances du rétroplanning et conserve l’avancement. Les dates des devis, acomptes et RSVP
restent celles saisies dans leurs fiches.

- Renseigne le client, l’étape commerciale et le budget prévu.
- Ajoute les prestataires, puis rattache chaque devis à son prestataire.
- Rattache les acomptes à des devis acceptés. Le budget engagé additionne les devis acceptés.
  Le total réglé additionne les acomptes marqués réglés.
- Saisis les invités, leur réponse et la date limite, puis prépare la feuille de route du jour J
  avec les horaires et responsables. Saisis le bilan dans le même dossier.

La section **Relances à traiter et historique** détecte les devis en attente, les acomptes à
régler et les RSVP en attente dont l’échéance est passée ou tombe dans les sept jours.
Elle crée au plus une relance par élément et date. Les brouillons sont actualisés quand on
relance la détection. Après validation, le lien de messagerie ouvre un brouillon adressé
au prestataire ou à l’invité. L’envoi se fait dans ta messagerie et le résultat est saisi
dans ORION. Les contacts sans e-mail peuvent être relancés par un autre canal et suivis
de la même façon. Le rapport quotidien en ligne de commande prépare aussi ces brouillons.

Les dossiers existants restent dans le même fichier SQLite. Les nouvelles tables sont créées
à la première ouverture du dossier détaillé ou lors de la détection des relances.

## Pilotage Wedding

En haut du suivi Wedding, **Pilotage Wedding** agrège les dossiers actifs. La synthèse
affiche les tâches en retard, à venir ou bloquées, les échéances métier, les relances
encore pertinentes et le solde engagé (devis acceptés moins acomptes réglés). Les dossiers
clôturés restent accessibles dans le sélecteur du rétroplanning.

Le bouton **Préparer les relances de tous les dossiers actifs** actualise les brouillons.
Ouvre le dossier concerné pour lire, valider ou écarter chaque relance.

## Brief quotidien

**Brief quotidien Wedding** affiche la dernière situation enregistrée et les dossiers
prioritaires. Il compare les retards et relances à valider avec le précédent brief
de même horizon, quand celui-ci existe. **Générer le brief du jour** actualise les
brouillons des dossiers actifs et enregistre la synthèse dans SQLite, à raison d’une
version par jour et par horizon. Les horaires affichés sont ceux de Paris.

Si le rappel Windows pointe déjà vers cette copie d’ORION et exécute
`backend.wedding_digest`, la prochaine exécution enregistre aussi le brief.
Pour l’utiliser via n8n, réimporte le workflow actualisé
`automations/n8n-wedding-quotidien.json` et publie-le. Il génère le brief après
avoir lu le rapport d’échéances. Une seule planification suffit.

## Mémoire d’un dossier

Sélectionne un mariage puis ouvre **Mémoire du dossier**. Ajoute une décision, un
compte rendu, une référence documentaire ou une idée. Tu peux indiquer une source
et rattacher la note à une tâche du rétroplanning. La recherche porte sur le titre,
le contenu et la source. Elle accepte les mots saisis sans accents.

Les notes restent dans la base SQLite Wedding. Le champ source conserve une référence,
comme un lien ou un nom de fichier. Les pièces jointes restent à intégrer.


### Workflow avec sources

Dans **Mémoire du dossier**, coche jusqu’à cinq notes dans les résultats de recherche
puis choisis un modèle Wedding et précise le livrable attendu. La sélection reste
disponible lorsque tu changes de page de résultats. Les notes choisies sont transmises
au modèle Ollama configuré comme sources de contexte. Les références [S1], [S2], etc.
renvoient aux versions enregistrées avec l’exécution. Vérifie les citations avant
d’utiliser le livrable. Le moteur local indique si l’exécution utilise Ollama ou la
simulation.

Le bloc **Exécutions récentes** donne accès aux résultats et aux versions des notes
transmises. Les notes sont dans la base SQLite Wedding. L’historique des exécutions
et leurs sources sont dans la base SQLite ORION. Sauvegarde les deux fichiers.

## Navigation du tableau de bord

**Pilotage** rassemble les indicateurs, les dossiers prioritaires et le brief quotidien.
**Dossiers** permet de créer ou de sélectionner un mariage, puis d’ouvrir sa fiche,
son rétroplanning ou sa mémoire avec les workflows à sources. **Modèles de workflows**
regroupe les modèles du cycle mariage disponibles pour une mission ponctuelle.

## Envoyer une relance depuis ORION

Le bouton **Envoyer par e-mail** apparaît sur une relance validée avec un destinataire
si le serveur SMTP est configuré. Relis le message, confirme le destinataire puis
lance l’envoi. Si des comptes Mémoire sont activés, saisis les identifiants d’un
administrateur dans le formulaire d’envoi.

Configure les variables suivantes dans l’environnement du processus ORION, puis
redémarre le serveur. Le transport utilise SMTP avec TLS implicite.

| Variable | Valeur |
|---|---|
| `ORION_SMTP_HOST` | Serveur SMTP du fournisseur |
| `ORION_SMTP_PORT` | Port TLS implicite, 465 par défaut |
| `ORION_SMTP_FROM` | Adresse d’expédition autorisée |
| `ORION_SMTP_USER` et `ORION_SMTP_PASSWORD` | Identifiants SMTP si requis par le fournisseur |

Après acceptation SMTP, le dossier conserve l’identifiant du message et l’heure
de la tentative. L’acceptation SMTP indique que le serveur a pris le message
en charge. Tu peux consigner une réponse ou tout autre résultat par la suite.
Si le résultat est incertain, vérifie ta messagerie avant de consigner le résultat.
ORION bloque un nouvel envoi par ce bouton dans cet état. Si ORION s’arrête en cours
d’envoi, le résultat peut être consigné après cinq minutes, après vérification.

L’option **Ouvrir dans la messagerie** reste disponible sur les relances validées.
