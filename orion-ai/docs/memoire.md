# Mémoire ORION

Ouvre **Mémoire** dans le menu du tableau de bord local pour saisir une note, une
décision, un compte rendu, un document texte ou une transcription. Le formulaire
peut lire les fichiers UTF-8 TXT, Markdown, VTT, SRT et CSV. Le contenu importé reste
modifiable avant l’enregistrement. ORION conserve le texte et la référence du fichier.

Associe l’élément à un site ou à un dossier Wedding existant. Renseigne la date de
la source et l’échéance quand elles sont connues. Si le dossier reste à déterminer,
garde l’élément dans **À classer** puis modifie-le plus tard.

La recherche porte sur le titre, le contenu et la source. Elle accepte les mots
sans accents. Affine avec les filtres de type et de classement.

**Exporter JSON** télécharge toutes les entrées de cette boîte, avec leur
identifiant, leur source et leur rattachement. La boîte de réception est incluse
dans la sauvegarde SQLite ORION décrite dans le guide d’exploitation locale.
L’export JSON conserve les entrées et les noms des pièces jointes. La sauvegarde
SQLite conserve aussi les fichiers originaux et les comptes.


## Questions et sources

Dans **Interroger la mémoire**, choisis un dossier via le filtre de classement ou
saisis des mots-clés, puis pose une question. ORION envoie jusqu’à cinq extraits
au modèle Ollama configuré. Les citations affichent le titre, la date de la source
si elle est renseignée, et l’extrait transmis. ORION refuse les réponses qui
omettent les références ou citent un identifiant absent du lot. Vérifie que les
extraits étayent bien les conclusions.

## PDF, images et audio

Le fichier original est conservé dans SQLite avec son texte extrait. La limite
d’enregistrement est de 16 Mio. Si l’extraction locale est indisponible ou
échoue, ORION conserve l’original et permet de compléter le texte manuellement.

- PDF texte et scans · Installe Poppler avec `pdftotext` et `pdftoppm`. Le texte
  est extrait des 100 premières pages. Un PDF sans texte peut être traité en
  OCR sur les cinq premières pages.
- JPEG et OCR des PDF · Installe Tesseract avec les données `fra` et `eng`.
  Tu peux modifier les langues via `ORION_OCR_LANG`.
- WAV, MP3, M4A, OGG et FLAC · Installe `ffmpeg` et `whisper-cli` (whisper.cpp).
  Indique le chemin du fichier modèle local avec `ORION_WHISPER_MODEL`.
  Les dix premières minutes sont transcrites. Les exécutables doivent être
  accessibles depuis le PATH du processus ORION.

## Comptes locaux

Crée le premier compte depuis le dossier du projet, dans PowerShell.

```powershell
py -3.12 -m scripts.orion_memoire_compte admin --role admin
py -3.12 -m scripts.orion_memoire_compte equipe --role member
```

Sur macOS et Linux, utilise `python3` ou le Python de l’environnement virtuel.
Dès la création du premier administrateur, l’espace Mémoire exige une connexion.
L’administrateur peut consulter toutes les entrées, y compris les entrées
antérieures à la création des comptes. Un membre consulte, interroge, modifie,
télécharge et exporte ses propres entrées. La session du tableau de bord prend fin
quand tu quittes l’espace Mémoire ou recharges la page. Garde ORION en local :
les autres modules et l’accès au fichier SQLite nécessitent leur propre gestion
des droits avant une mise en réseau.
