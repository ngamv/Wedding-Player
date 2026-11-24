# Brief du CEO

Ouvre **Brief du CEO** dans le tableau de bord et clique sur **Générer le brief du jour**.
Le rapport rapproche les dossiers Wedding actifs à surveiller, les interventions web
à valider ou vérifier, les derniers échecs par workflow web et les échéances de la
Mémoire arrivées à terme ou prévues dans les sept prochains jours. Les points urgents
sont affichés en premier. Le lien ouvre le site, le dossier Wedding ou l’entrée Mémoire.

Pour retirer une échéance Mémoire une fois traitée, vide le champ Échéance de l’entrée.
Une source indisponible est signalée et les autres restent lisibles. Le brief compare
le total des priorités avec le précédent rapport complet quand les deux rapports
affichés sont complets. SQLite conserve un instantané par jour. Si des comptes Mémoire
sont activés, le brief consolidé est réservé aux administrateurs.

## Planifier sur Windows

Depuis PowerShell, dans le dossier ORION, teste la commande de génération puis
crée une tâche quotidienne. L’horaire par défaut est fixé à 09 h 15, heure locale
du PC. La tâche tourne sous ton compte quand ta session est ouverte.

```powershell
py -3.12 -m backend.ceo_digest
.\scripts\installer_brief_ceo.ps1
```

Sur macOS ou Linux, utilise la commande équivalente `python3 -m backend.ceo_digest`
avec le Python de l’environnement ORION. Le serveur web peut être arrêté pendant
la génération. Si tu utilises un chemin SQLite personnalisé, configure le même
environnement dans le processus planifié et dans le serveur web.

Le brief utilise les données locales. Les connecteurs CRM, agenda, support et
facturation restent à raccorder.

## Importer les données métier

Dans **Brief du CEO → Imports métier**, choisis la catégorie et télécharge son
modèle. Prépare un CSV UTF-8, séparé par des points-virgules ou des virgules.
Les champs requis sont `id`, `title`, `date` (AAAA-MM-JJ) et `status`.
Les encaissements exigent aussi `amount_eur`, avec deux décimales au maximum.

| Catégorie | Statuts acceptés | Date attendue |
|---|---|---|
| Prospects | `new`, `contacted`, `closed` | Date d’entrée dans le CRM |
| Rendez-vous | `scheduled`, `done`, `cancelled` | Date du rendez-vous |
| Tickets | `open`, `urgent`, `closed` | Date d’ouverture |
| Encaissements | `paid`, `pending`, `cancelled` | Date effective du paiement pour `paid` |

Conserve le même identifiant quand un élément évolue. Un nouvel import met à
jour les éléments présents et conserve les autres. Pour clôturer ou annuler un
élément, réimporte-le avec son nouveau statut. Une ligne invalide fait rejeter
le fichier entier. Le dernier résultat par catégorie reste visible.

Génère un brief après l’import pour actualiser ses indicateurs et ses priorités.
Ce mode de raccordement utilise les exports CSV préparés à partir de tes outils.

### Synchronisation avant chaque brief

Crée un dossier `imports` à la racine d’ORION et dépose les exports CSV sous les
noms `prospects.csv`, `appointments.csv`, `tickets.csv` ou `receipts.csv`.
La variable `ORION_IMPORT_DIR` permet de sélectionner un autre dossier. Mets à
jour les fichiers avant l’exécution planifiée, idéalement en préparant l’export
à part puis en remplaçant le fichier terminé.

La génération du brief, manuelle ou planifiée, lit les fichiers présents.
Un fichier inchangé ne réécrit pas les données. Un fichier corrigé est traité à la
génération suivante. Les fichiers illisibles, rejetés ou auparavant suivis puis
retirés sont signalés dans **Synchronisation des fichiers locaux**. Les dernières
données valides restent disponibles. Le processus planifié renvoie un code d’échec
si un fichier pose problème, et le brief reste consultable.

Le raccordement direct aux API de tes outils reste à configurer. En attendant,
un export planifié par l’outil source peut alimenter ce dossier.

## Journal des générations

Le bouton de génération place la demande dans une file SQLite. Une demande
simultanée pour le même jour utilise la génération déjà en attente ou en cours.
Le Planificateur Windows utilise la même file. Le journal indique l’origine,
l’heure et le résultat de chaque tentative récente.

Si une source échoue, le brief partiel reste consultable et le journal indique
la source à vérifier. Corrige-la, puis clique sur **Relancer la génération**.
Une demande encore en attente après un redémarrage reprend à la réouverture du
brief. Une génération interrompue en cours est signalée après quinze minutes
et peut être relancée. Ce journal couvre le brief CEO.

### Suivre les encaissements

Dans **Finances**, choisis une période de 30, 60 ou 90 jours. Le relevé affiche
les encaissements, les paiements en attente et les encaissements de la période
précédente de même durée. Le filtre de statut s’applique au détail des écritures.
Les montants proviennent des imports d’encaissements et s’affichent en euros.
La date d’une ligne en attente peut servir de date prévue. Le relevé suit les
paiements, tandis que le chiffre d’affaires facturé dépend des données de facturation.

## Vue d’ensemble

La page d’accueil affiche les encaissements importés, les tickets ouverts, les projets
actifs, les dossiers Wedding et les sites enregistrés. Clique sur une carte pour
ouvrir son module. Les encaissements utilisent une période sélectionnable de 30,
60 ou 90 jours. Un premier import manquant ou un import en échec est signalé.

Les priorités affichées viennent du dernier brief enregistré. Génère un nouveau
brief pour les mettre à jour après un changement important. Le bouton **Exporter CSV**
exporte les indicateurs affichés. Si les comptes Mémoire sont activés, la vue
consolidée est réservée aux administrateurs.

## Espace Validations

Dans **Validations**, retrouve les brouillons de relance Wedding encore valides
et les plans d’intervention web à examiner. Les relances dont l’échéance est
atteinte apparaissent en premier. Le filtre permet de se concentrer sur une
activité.

**Examiner** ouvre la relance ou l’intervention dans son module. Les décisions
se prennent dans la fiche, où le contenu complet et les actions sont disponibles.
Les propositions déjà traitées et les relances devenues obsolètes quittent la
liste. Avec les comptes activés, cette vue consolidée est réservée aux administrateurs.

Dans le filtre **Étape**, choisis **À suivre après validation** pour retrouver les
plans web dont le contrôle reste à consigner et les relances Wedding à traiter ou
à vérifier. Les décisions et résultats restent disponibles dans leurs fiches.

Dans une intervention web au stade **À valider**, **Écarter ce plan** permet de
consigner un refus avec son motif. Le plan quitte la liste de validation et reste
consultable dans le journal du site.

Le filtre **Historique** rassemble les décisions et résultats déjà enregistrés,
y compris pour les dossiers Wedding clôturés. Il affiche la date connue et un
lien vers la fiche. Les raisons du refus et les détails du résultat restent
consultables dans la fiche d’origine.

## Recherche transversale

Le lien **Rechercher** dans l’en-tête permet de retrouver les projets, tâches,
tickets, dossiers Wedding, sites et entrées Mémoire. Saisis un mot-clé ou la
référence d’un ticket, puis filtre par type si nécessaire. Les accents et la
casse sont ignorés. Chaque résultat ouvre sa fiche, et une tâche est dépliée
directement dans son projet.

La recherche peut rapprocher un mot du contenu d’une entrée Mémoire. La liste
affiche son titre et sa date. Avec les comptes activés, la recherche transversale
est réservée aux administrateurs. Les membres utilisent leur propre recherche
dans Mémoire.
