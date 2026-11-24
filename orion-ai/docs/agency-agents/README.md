# Agency Agents dans ORION

Source https://github.com/msitarzewski/agency-agents à la révision `8ae6164602c95ca78828b148b9052460ee426885`. Licence MIT jointe.

281 agents sont disponibles dans Claude Code au niveau du projet. Le préfixe `agency-` identifie les profils importés. Utilisez `/agents` ou demandez par exemple le sous-agent `agency-engineering-frontend-developer`. Le modèle actif est hérité de la session.

Les profils de test d’intrusion et le profil AppSec dont le guide demande des exercices d’exploitation sont exclus. Les profils défensifs de surveillance et de détection restent disponibles.

Le moteur IA local charge aussi 281 profils Agency depuis `agents/agency/`. Les profils moteur reprennent le titre et la spécialité des agents, avec une consigne textuelle adaptée au moteur ORION. Dans les workflows, sélectionnez ces agents comme les autres profils. Dans le catalogue en ligne, filtrez sur l’équipe `agency`. Vercel permet la simulation dans le navigateur. Ollama utilise le modèle défini sur le serveur local ORION.
