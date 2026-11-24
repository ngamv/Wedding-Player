# Agenda ORION

L’onglet **Agenda** regroupe les rendez-vous importés, les dates de mariage,
les échéances des projets actifs et celles de leurs tâches ouvertes. Choisis une
date de départ, un horizon de 7, 30 ou 90 jours et un type d’événement.

Les liens des projets, tâches et mariages ouvrent les fiches correspondantes.
Les rendez-vous importés renvoient à la page des imports CSV. Pour mettre à jour
un rendez-vous, un mariage ou une échéance, utilise le module source puis recharge
l’agenda. Les exports de rendez-vous actuels contiennent une date sans heure.
Si des comptes sont activés, l’agenda est réservé à l’administrateur.

## Export iCalendar

Choisis la date de départ, l’horizon et le type d’événement, puis clique sur
**Exporter iCalendar**. Le fichier `.ics` reprend tous les événements qui
correspondent aux filtres et s’importe dans Outlook, Google Agenda ou Apple
Calendrier. Les rendez-vous locaux conservent leur horaire. Les rendez-vous CSV,
mariages et échéances sans heure sont exportés sur la journée entière.

Le fichier représente l’état de l’agenda au moment de l’export. Les modifications
ultérieures dans ORION exigent un nouvel export. Le traitement d’un réimport
dépend de l’application de calendrier. L’export inclut le titre et, lorsqu’il est
disponible, le responsable ou le contexte affiché dans l’agenda.


## Rendez-vous locaux

Dans **Nouveau rendez-vous**, saisis une date, une heure à Paris et une durée.
La liste permet ensuite de modifier ou d’annuler le rendez-vous. Le filtre
**Inclure les rendez-vous locaux annulés** les rend accessibles pour consultation
ou replanification. Les rendez-vous annulés sont écartés de l’export iCalendar
et du Brief du CEO.

Les heures ambiguës ou inexistantes au changement d’heure sont refusées. La
durée est enregistrée en minutes réelles. La saisie reste locale à ORION et
ne crée aucune invitation dans un agenda externe.

### Dossiers associés et conflits

Le formulaire de rendez-vous permet de sélectionner un projet ou un dossier
Wedding. L’agenda affiche un lien vers le dossier, et le Brief du CEO ouvre
directement les rendez-vous saisis dans ORION.

Deux rendez-vous locaux prévus qui se chevauchent sont signalés dans l’agenda.
Les créneaux adjacents et les rendez-vous annulés sont exclus de ce contrôle.
Les rendez-vous CSV sans horaire ne participent pas au contrôle. L’avertissement
laisse la possibilité de conserver un chevauchement volontaire.
