# Pilotage des sites web

Dans le tableau de bord local, ouvre **Site web** et enregistre le nom, l’URL,
l’objectif et le CMS ou l’hébergeur. Si le code est dans un dépôt GitHub public,
saisis son identifiant `organisation/depot` et clique sur **Synchroniser GitHub**.
ORION enregistre les métadonnées du dépôt, la branche par défaut et l’heure de
synchronisation. L’URL publique est enregistrée dans le dossier et s’ouvre dans
un nouvel onglet.

Sept modèles couvrent le raccordement, l’audit, le contenu et le SEO, les
évolutions, la mise en ligne, le suivi des incidents et la mesure. Les procédures
correspondantes sont dans `.claude/skills/site-*/SKILL.md`.

Chaque intervention se déroule en trois temps.

1. Génère une proposition avec le modèle adapté et un brief factuel.
2. Consulte les résultats de chaque agent, puis valide le plan si celui-ci est prêt.
3. Effectue l’intervention dans l’outil concerné et consigne le résultat des contrôles.

Le journal conserve l’état et les dates de validation et de vérification dans la
base SQLite ORION. Une simulation permet de tester le parcours de génération.
Active Ollama pour obtenir des propositions à valider.

Le premier connecteur est en lecture seule et couvre les dépôts GitHub publics.
La gestion des dépôts privés, la publication dans le CMS, les déploiements et
la collecte automatique des mesures dépendent des outils du site à raccorder.
