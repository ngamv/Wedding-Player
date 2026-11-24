# Registre des projets

Dans **Projets**, crée une fiche avec un nom, un responsable et, si elle est connue,
une échéance. Change le statut au fil de l’avancement. Pour un projet bloqué,
indique la cause ou la décision attendue dans le point de suivi. Chaque
enregistrement conserve son statut, sa note, son auteur et son heure dans l’historique.

Le Brief du CEO affiche les projets bloqués ou en retard en priorité, ainsi que
les échéances à sept jours. Les liens ouvrent directement les fiches concernées.
Un projet terminé disparaît des priorités lors de la prochaine génération.

Les fiches et l’historique sont conservés dans la base SQLite d’ORION. Si les
comptes Mémoire sont activés, le registre est réservé à l’administrateur.

## Suivre les tâches

Ouvre une fiche enregistrée, puis **Nouvelle tâche**. Chaque tâche a son propre
responsable, son échéance et son statut. Un blocage doit être décrit dans le
point de suivi. La barre d’avancement indique le nombre de tâches terminées.

Dans le brief, ORION regroupe les alertes de tâches sous le projet concerné.
Un blocage ou un retard rend le projet urgent même si sa propre échéance est
encore lointaine. Les tâches terminées et celles d’un projet terminé sortent
des alertes à la prochaine génération.

## Mémoire du projet

Depuis une fiche, **Ouvrir la mémoire de ce projet** présélectionne le projet dans
le formulaire de capture et dans le filtre de recherche. Ajoute une décision, un
document ou un compte rendu en indiquant sa date de source. La fiche affiche les
dix derniers éléments rattachés et permet d’ouvrir chacun dans Mémoire.

Pour demander une synthèse ou retrouver une décision, garde le projet sélectionné
dans le filtre et utilise **Interroger la mémoire**. Ollama reçoit uniquement les
extraits retenus dans ce périmètre. Avec les comptes activés, le rattachement et la
consultation de cette mémoire sont réservés à l’administrateur.

## Dépendances entre tâches

Ouvre **Prérequis** dans le formulaire de la tâche et coche les travaux à terminer
au préalable. ORION affiche les prérequis encore ouverts et empêche la clôture
de la tâche tant qu’ils restent ouverts. Les liens circulaires sont refusés.
Pour rouvrir un prérequis, rouvre d’abord les tâches terminées qui en dépendent.

Le brief indique le nombre de tâches en attente de prérequis quand elles sont
bloquées ou à échéance dans son horizon de sept jours, retards compris.

## Planning transversal

Dans **Projets → Planning des tâches**, filtre les tâches ouvertes par responsable,
retard, échéance à sept jours, blocage ou absence d’échéance. Les tâches en attente
d’un prérequis apparaissent dans **Bloquées ou en attente**. Les tâches terminées et
celles des projets terminés sont écartées du planning. **Ouvrir** déplie directement
la tâche dans sa fiche projet.
