# Wingfoilscout

*Ce guide en : [English](README.md) · [Deutsch](README.de.md) · **Français** · [Español](README.es.md)*

Trouve des sessions de wingfoil autour de toi et écrit un rapport HTML :
**où ça souffle, quand, avec quelle wing — et si le trajet vaut le coup.**

Il combine trois modèles météo (plus un ensemble pour la fiabilité) avec la
connaissance de 278 spots : secteurs de vent, géométrie du rivage issue
d’OpenStreetMap, marées, vents thermiques, temps de trajet. Il tourne en local
sur ton propre ordinateur, sans compte et sans paquets tiers à part PyYAML.
Toutes les vitesses de vent sont en **nœuds**. L’interface parle anglais,
allemand, français et espagnol.

<p align="center">
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/bilder/en/search-dark.png"><img src="docs/bilder/en/search-light.png" width="250" alt="Recherche : point de départ, heure de début et trois préréglages"></picture>
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/bilder/en/destinations-dark.png"><img src="docs/bilder/en/destinations-light.png" width="250" alt="Les trois meilleures destinations"></picture>
<picture><source media="(prefers-color-scheme: dark)" srcset="docs/bilder/en/grid-dark.png"><img src="docs/bilder/en/grid-light.png" width="250" alt="Grille horaire : chaque spot, heure par heure"></picture>
</p>
<p align="center"><sub>Vue d’exemple avec des données météo inventées ·
<a href="https://darkpiratego.github.io/wingfoilscout/">Site web</a> ·
<a href="https://darkpiratego.github.io/wingfoilscout/demo.html">Rapport d’exemple</a></sub></p>

Jusqu’à la version 2.0, le projet s’appelait **Wingscout** ; les anciennes
entrées du changelog et des rapports de revue et d’audit portent encore ce nom.
En interne, le paquet Python s’appelle toujours `wingscout` — c’est pour ça
que les commandes ci-dessous s’écrivent ainsi.

La version actuelle figure dans `wingscout/__init__.py`, sous le logo à droite de la barre d’onglets de chaque page et en pied de chaque rapport · comment Wingfoilscout décide : [`SCORING.md`](SCORING.md) · modifications dans [`CHANGELOG.md`](CHANGELOG.md) (anciennes entrées en allemand) · points ouverts dans [`REVIEW.md`](REVIEW.md) (en allemand, historique) · licence : [PolyForm Noncommercial 1.0.0](LICENSE) (© 2026 DARK)

---

## Installation

### Sur Mac, avec le Terminal (recommandé)

Deux lignes à coller dans le **Terminal** — il se trouve dans Applications →
Utilitaires, ou tape « Terminal » dans Spotlight :

1. **Une fois par Mac : les outils en ligne de commande d’Apple.** Ils
   apportent Python et `git` :

   ```bash
   xcode-select --install
   ```

   Une fenêtre demande s’il faut les installer : clique sur **Installer**,
   accepte la licence et attends le message indiquant que le logiciel a été
   installé — cela prend quelques minutes. Si le Terminal répond que les
   outils sont déjà installés, passe directement à la suite.

2. **Récupérer Wingfoilscout et le lancer :**

   ```bash
   cd ~ && git clone https://github.com/DarkPirateGo/wingfoilscout.git && cd wingfoilscout && bash "Wingfoilscout starten.command"
   ```

   Colle toute la ligne d’un coup ; chaque partie ne s’exécute que si la
   précédente a réussi. Elle crée le dossier `wingfoilscout` dans ton
   dossier personnel, installe PyYAML la première fois et ouvre l’interface
   dans le navigateur.

Ensuite, tu lances Wingfoilscout d’un double-clic sur **« Wingfoilscout
starten »** (en français : « Lancer Wingfoilscout ») dans ce dossier, et tu
récupères les nouvelles versions d’un double-clic sur **« Neuen Stand
holen »** — tous les fichiers à double-cliquer sont expliqués
[plus bas](#fichiers-à-double-cliquer). Ce que `git` a récupéré n’est pas
passé par le navigateur : macOS ne le bloque donc pas.

Tu choisis le point de départ dans l’interface. Ton matériel, tu le saisis
une fois dans `config.yaml` — un fichier texte du même dossier, créé à
partir de `config.example.yaml` au premier lancement.

### Sur Mac, sans Terminal

1. Sur la [page de la dernière version](https://github.com/DarkPirateGo/wingfoilscout/releases/latest),
   télécharge **Source code (zip)** sous « Assets » et décompresse-le d’un
   double-clic, si le navigateur ne l’a pas déjà fait.
2. Dans le dossier, double-clique sur **« Wingfoilscout starten »**. La
   première fois, macOS refuse et indique qu’Apple n’a pas pu vérifier que
   le fichier est exempt de logiciel malveillant — il vient d’Internet et
   n’est pas signé par un développeur enregistré auprès d’Apple. Ferme le
   message.
3. Ouvre **Réglages Système → Confidentialité et sécurité** et descends
   jusqu’à **Sécurité** : il y est indiqué que « Wingfoilscout
   starten.command » a été bloqué. Clique sur **Ouvrir quand même**,
   confirme avec ton mot de passe si on te le demande, puis clique sur
   **Ouvrir** quand l’avertissement réapparaît. Jusqu’à macOS 14, clic droit
   sur le fichier → **Ouvrir** suffit.
4. Si macOS demande si le Terminal peut accéder au dossier
   « Téléchargements », autorise-le. S’il propose d’installer les **outils
   de développement en ligne de commande** : installe-les — ils apportent
   Python —, attends la fin et double-clique à nouveau ; le script de
   lancement reconnaît ce cas et te le signale.
5. Au premier lancement, le script installe PyYAML ; ensuite, l’interface
   s’ouvre dans le navigateur.

Chaque fichier à double-cliquer demande une fois l’étape 3, « Wingfoilscout
fürs iPhone starten » compris. Par ce chemin, les nouvelles versions
n’arrivent que sous forme de nouveau ZIP : copie `config.yaml`,
`tagebuch.json`, `modellguete.json`, `ui_defaults.json` et `sprache.txt` de
l’ancien dossier dans le nouveau. Les spots que tu as ajoutés toi-même
restent dans le `spots.yaml` de l’ancien dossier — le chemin par le Terminal
les garde lors des mises à jour.

### À la main, ou sous Windows et Linux

Avec Python 3.9 ou plus récent et `git` :

```bash
git clone https://github.com/DarkPirateGo/wingfoilscout.git
cd wingfoilscout
python3 -m pip install -r requirements.txt      # PyYAML uniquement
tools/install-hooks.sh                          # facultatif : contrôle avant chaque commit
python3 -m wingscout.webui                      # démarrage : ouvre l’interface dans le navigateur
```

Sur Mac, Python 3.9 et `git` viennent avec les outils en ligne de commande
d’Apple (étape 1 ci-dessus). Aucune autre dépendance que PyYAML : les
données météo arrivent par la bibliothèque standard, et le rapport est un
seul fichier HTML. Sous Windows, `wingfoilscout.bat` lance l’interface (non
testé).

Le Python d’Apple a toutefois une limite : il est compilé avec LibreSSL 2.8.3,
qui date de 2018. Avec lui, aucune connexion au serveur d’itinéraires
n’aboutit ; le journal d’exécution affiche `SSLV3_ALERT_HANDSHAKE_FAILURE`, et
le trajet reste une estimation : distance à vol d’oiseau multipliée par un
facteur. La météo et le rapport ne sont pas concernés. Pour savoir si c’est
ton cas, lance

```bash
python3 -c "import ssl; print(ssl.OPENSSL_VERSION)"
```

S’il affiche *LibreSSL*, un Python récent règle le problème (`brew install python` ou
l’installeur de python.org, puis une **nouvelle** fenêtre de terminal) ;
celui-ci est livré avec OpenSSL 3. S’il affiche *OpenSSL*, tout va bien.

Ensuite, adapte `config.yaml` : `rider.home` à ton propre point de départ,
`quiver.wings` à ton propre matériel. Le fichier est entièrement commenté ;
tout ce qu’il contient est fait pour être modifié.

### Fichiers à double-cliquer

Le dossier contient quelques fichiers à double-cliquer dans le Finder sur Mac,
plus `wingfoilscout.bat` pour Windows. Ils gardent leur nom allemand ; ce
guide les désigne sans l’extension `.command`.

| Fichier | En français | Ce qu’il fait |
|---|---|---|
| `Wingfoilscout starten.command` | Lancer Wingfoilscout | ouvre l’interface dans le navigateur ; installe d’abord PyYAML s’il manque |
| `Wingfoilscout fürs iPhone starten.command` | Lancer Wingfoilscout pour l’iPhone | pareil, mais l’interface est aussi accessible depuis un iPhone sur le même Wi-Fi (voir [Sur l’iPhone](#sur-liphone)) |
| `wingfoilscout.bat` | — | Windows : ouvre l’interface dans le navigateur |
| `Neuen Stand holen.command` | Récupérer la dernière version | récupère l’état actuel depuis GitHub sans perdre tes propres modifications, puis lance les tests (nécessite un clone `git`) |
| `Auf GitHub veröffentlichen.command` | Publier sur GitHub | contrôle, commit et push — pour les contributeurs |
| `Tests ausführen.command` | Lancer les tests | le contrôle complet avec tous les tests (`tools/check.sh`) |
| `Ufergeometrie berechnen.command` | Calculer la géométrie du rivage | exécution ponctuelle de `build_geometry.py` (voir [Géométrie du rivage](#géométrie-du-rivage)) |
| `Prüfstand.command` | Banc d’essai | lance `tools/pruefstand.py` (voir [Le banc d’essai](#le-banc-dessai--vérifier-que-tout-est-encore-juste)) |

## Utilisation

**Sans terminal :** double-clique sur **« Wingfoilscout starten »** dans le
Finder (sous Windows : `wingfoilscout.bat`). Une interface s’ouvre dans le
navigateur. En haut, il n’y a que deux questions — **Au départ d’où ?** et
**À partir de quand ?** — et en dessous trois préréglages :

| | Jours | Nuits | Rayon |
|---|---|---|---|
| **Spontané** | 2 | – | 250 km |
| **Week-end** | 3 | – | 500 km |
| **Avec nuitée** | 4 | 2 d’affilée | 1000 km |

Choisis-en un, appuie sur **« Chercher des spots »**, et le rapport apparaît
en dessous. En général, c’est tout ce que tu as à faire. Les jours comptent à
partir de maintenant — ou du début choisi, si tu en indiques un (voir
[Début de la recherche](#début-de-la-recherche)).

Tout ce qui est plus détaillé se trouve dans trois sections dépliables, qui
gardent leurs valeurs :

- **Affiner la recherche** — période, rayon, nuits, temps de trajet, ce qui
  compte comme session, limites de température et de rafales, aversion au
  clapot, herbiers, types de plans d’eau. Si tu changes quelque chose ici, le
  préréglage est désélectionné et une ligne en dessous indique ce qui
  s’applique actuellement.
- **Sources de données** — géométrie du rivage, calcul d’itinéraire,
  ensemble, emplacements pour la nuit, données marines, alertes, mode démo.
  C’est aussi là que se trouve le bouton **« Calculer les manquants »** pour
  la géométrie du rivage, avec à côté le nombre de spots qui en manquent
  encore.
- **Ajouter des spots** — voir plus bas.

Trois champs portent un point d’interrogation avec une courte explication :
**Note minimale**, **Taux de rafales max.** et **Aversion au clapot**. Leur
nom ne parle pas de lui-même, et dans le rapport ils réapparaissent sous forme
de nombre.

**« Enregistrer par défaut »** mémorise tes saisies comme nouvelles valeurs de
départ (dans `ui_defaults.json` ; ton `config.yaml` commenté reste intact).

**Langue :** l’interface et le rapport existent en anglais, allemand,
français et espagnol. Le sélecteur (DE · EN · FR · ES) se trouve à côté du
logo en haut à droite — sur téléphone, en pied de page. Ton
choix est enregistré dans `sprache.txt` dans le dossier Wingfoilscout et
s’applique tout de suite à toutes les pages — « Destinations » comprise :
chaque recherche enregistre son rapport dans les quatre langues (dans
`cache/report/`), changer de langue ne demande donc pas de nouvelle
recherche. Seul le fichier `report.html`, celui que tu peux envoyer par
AirDrop sur ton téléphone, reste dans la langue de la recherche ; un rapport
d’avant 2.3.0 n’existe que dans une langue jusqu’à la prochaine recherche.
Tant que tu n’as rien
choisi, Wingfoilscout suit ton navigateur : la première des quatre langues
dans l’ordre de préférence de ton navigateur — l’anglais s’il n’en demande
aucune, l’allemand s’il n’envoie aucune langue. La variable d’environnement
`WINGSCOUT_SPRACHE` (`de`, `en`, `fr` ou `es`) l’emporte sur les deux. Les
nombres, les dates et les heures s’affichent selon les usages de la langue (en
français 4,2 et 20 sept. 2026 19:09). La ligne de commande et les fenêtres de
terminal des fichiers à double-cliquer choisissent leur langue elles-mêmes,
voir [Ligne de commande](#ligne-de-commande).

**Aide dans l’app :** le bouton **?** en haut à droite de chaque page (sur
téléphone, à côté de « Quitter ») ouvre ce guide et la page illustrée
« Comment Wingfoilscout calcule » — dans la langue que tu as choisie.

Une limite : ce qui vient des données et non du programme reste dans sa
langue d’origine, le plus souvent l’allemand — noms des spots, remarques et
autres textes du catalogue (`spots.yaml`), ainsi que certains noms de lieux et
de zones issus d’OpenStreetMap.

Après **« Neuen Stand holen »** (récupérer la dernière version), une interface
déjà ouverte continue d’exécuter l’ancien code jusqu’à ce que tu quittes
Wingfoilscout et le relances — chaque page l’indique alors par un bandeau. Et
l’onglet Bilan affiche son dernier résultat quand tu l’ouvres ; s’il est plus
ancien que la dernière recherche ou a été calculé avec une version antérieure,
un message au-dessus le signale, et « Vérifier » le recalcule.

### Point de départ en route

En haut de l’interface, il y a **Au départ d’où ?**. Laissé vide, Wingfoilscout
calcule depuis ton domicile, `rider.home` dans `config.yaml` (le fichier
d’exemple contient le centre de Hambourg comme valeur provisoire). Si tu
saisis quelque chose, le rayon, la distance et le temps de trajet partent de
ce point — c’est le cas quand tu es déjà en route et veux savoir ce qui est
possible depuis *ici*.

Les formats reconnus sont les degrés décimaux (`51.7625, 3.854` — virgule ou
point décimal), les degrés/minutes/secondes (`51°45'45"N 3°51'14"E`) et un lien
Google Maps collé. Un nom de lieu (« Hambourg ») n’en fait pas partie : depuis
la 1.19.0, Wingfoilscout le refuse avant de démarrer et dit ce qui fonctionne
— avant, la recherche partait sans rien dire du domicile. Le bandeau à la fin
indique le point de départ utilisé.

Il y a aussi deux boutons. **« Carte »** ouvre une carte : clique dedans ou
fais glisser l’épingle, c’est fait — c’est la méthode qui marche toujours, tant
que tu as une connexion. **« Ici »** demande ta position au navigateur ; c’est
plus pratique, mais ça ne marche que si le système d’exploitation fournit une
position.
Safari sous macOS ne répond parfois pas du tout (délai dépassé), typiquement
quand le Wi-Fi est coupé — les Mac se localisent grâce aux réseaux Wi-Fi
alentour, pas par GPS. Le message sous le bouton t’indique la cause.

Le point de départ n’est volontairement **pas** mémorisé par « Enregistrer par défaut » — il vaut pour aujourd’hui et ici, pas pour le prochain lancement. En
ligne de commande, la même chose fonctionne avec `--start "51.7625, 3.854"` et,
en option, `--start-name Brouwersdam`.

### Début de la recherche

Sous le point de départ, l’interface demande **À partir de quand ?**.
Laissé vide, la recherche commence maintenant, comme toujours. Si tu choisis
une date et une heure — samedi 9:00 par exemple —, les jours du préréglage
comptent à partir de ce jour, et les heures d’avant apparaissent grisées dans
la grille horaire comme « avant le début choisi » : dès le mercredi, tu
peux ne regarder que le week-end.

Les prévisions vont jusqu’à 16 jours à partir d’aujourd’hui ; le champ
indique jusqu’à quand. Si le début plus les jours vont au-delà, la recherche
raccourcit la période et le signale dans le journal d’exécution. L’heure est
celle de ton ordinateur ; pour chaque spot, elle est convertie en heure
locale, comme toutes les heures du rapport. **« Maintenant »** vide le
champ. Comme le point de départ, le début n’est **pas** mémorisé par
« Enregistrer par défaut ». En ligne de commande : `--ab "2026-10-10 09:00"`
(ou `10.10.2026 09:00`, ou seulement la date).

### Ajouter des spots

Dans la section **Ajouter des spots**. Une ligne par spot, dans n’importe
quelle notation rencontrée en route :

```
Hardtsee; 49.17008, 8.61477
49.17008, 8.61477 Hardtsee
Bostalsee; 49.56831, 7.07964; reservoir
https://www.google.com/maps/@51.7625,3.854,15z
```

Le nom avant ou après, le type de plan d’eau en option comme dernier champ
(`sea`, `lagoon`, `lake`, `reservoir`). Les degrés/minutes/secondes sont
reconnus aussi. Le champ fichier accepte en plus les formats d’export
courants : **GPX** (waypoints), **KML** de Google My Maps (repères),
**GeoJSON** de Google Takeout et **CSV** avec des colonnes pour la latitude et
la longitude. Un fichier KMZ est un KML zippé — décompresse-le et charge le
`doc.kml` qu’il contient.

Attention aux listes Google issues de Takeout : leur CSV ne contient souvent
que le titre, la remarque et une adresse Maps avec un identifiant de lieu, mais
pas de coordonnées. Si le lien contient une position (`.../@51.7625,3.854,15z`),
elle est utilisée ; sinon la ligne est ignorée et comptée. Un identifiant de
lieu ne se convertit pas en coordonnées sans interroger Google, et rien n’est
deviné ici. Les points à moins de 300 m d’un spot existant sont ignorés et
signalés.

Les spots sont ajoutés à `spots.yaml` et comptent dès la prochaine recherche.
Si la case **Calculer aussi la géométrie du rivage** est cochée, la géométrie
des nouveaux spots est récupérée juste après — environ un quart de minute par
spot.

Pour ce qui reste en suspens, il y a le bouton **Calculer les manquants** dans
les Sources de données. À côté, tu vois combien de spots n’ont pas encore de
géométrie. Le calcul parcourt le catalogue dans l’ordre, enregistre après
chaque spot et affiche sa progression dans le même journal d’exécution ;
l’interrompre ne pose aucun problème, et le clic suivant reprend avec les
spots restants. Le script `build_geometry.py` fait la même chose et existe
toujours pour la ligne de commande — mais il n’est plus nécessaire.

Trois choses sont devinées au passage, et tu devrais les vérifier : le type
de plan d’eau (par défaut `lake`), le fond (`shallow: none`, `seagrass: none`)
et le code pays, qui vient de rectangles approximatifs par pays et peut être faux
près des frontières — il détermine seulement quel flux d’alertes s’applique.
Les secteurs de vent restent vides ; la géométrie du rivage les fournit.

### Proposer un spot à tous

Les spots que tu ajoutes toi-même restent sur ton ordinateur. Pour qu’un spot
entre dans le catalogue de tous, il y a **« Proposer à tous »** — dans le
volet **Ajouter des spots** et sous **« Ajouter un nouveau spot »** dans le
catalogue. Il ouvre un formulaire sur GitHub ; dans le catalogue, celui-ci
est déjà rempli avec ce que tu as saisi au-dessus (nom, coordonnées,
remarque). À côté de chaque spot du catalogue,
**proposer une correction** fait de même pour un spot qui existe déjà. Il
faut un compte GitHub gratuit, et rien n’est envoyé tant que tu n’as pas
soumis le formulaire là-bas. Il demande le plan d’eau, les bonnes directions
de vent, ce que les autres devraient savoir et d’où vient ce que tu sais. Le
formulaire s’ouvre aussi directement :
https://github.com/DarkPirateGo/wingfoilscout/issues/new?template=spot.yml

Chaque proposition est vérifiée à la main et entre dans le catalogue de la
version suivante — tous ceux qui mettent à jour la reçoivent. En l’envoyant,
tu acceptes qu’elle soit publiée sous la licence de Wingfoilscout et que DARK
puisse aussi l’utiliser sous d’autres conditions
([CONTRIBUTING.md](CONTRIBUTING.md)).

### Vérifier les coordonnées

Sous **Sources de données**, un bouton **« Vérifier les coordonnées »**
apparaît dès qu’il y a quelque chose à vérifier ; de même pour l’onglet du
même nom en haut (depuis la 1.16.1, seulement dans ce cas — s’il n’y a rien en
attente, il disparaît, et la page reste accessible sous `/pruefen`). Il ouvre
une page à part : une carte à gauche, à droite les spots à examiner. Un filtre
au-dessus de la liste distingue trois niveaux :

- **Inutilisables** — au plus 100 à 300 m d’eau dans *toutes* les
  directions. L’épingle est alors presque sûrement à terre, sur un parking ou
  dans le mauvais plan d’eau.
- **Douteux** — déplacés de plus d’un kilomètre de l’épingle vers l’eau.
  Utilisables, mais l’épingle est décalée.
- **Non confirmés** — `verified: false` : les coordonnées viennent d’une
  liste importée et personne ne les a jamais regardées. Pour la liste
  Takeout, l’écart va jusqu’à environ un kilomètre, parce que la colonne y
  était arrondie. Ce n’est pas une erreur, juste une question ouverte — ces
  spots sont triés par distance au point de départ, les plus proches d’abord,
  parce que ce sont ceux que tu as le plus de chances de connaître toi-même.

Les deux boutons écrivent dans `spots.yaml` : **« Appliquer »** enregistre les
nouvelles coordonnées, **« C’est bon »** confirme les existantes. Les deux
mettent `verified: true` — qui a placé l’épingle lui-même ou regardé le point
l’a vérifié. `geo_ok: true` n’est ajouté que là où il y a vraiment un
avertissement de géométrie.

Ce qui compte, c’est ce qui n’est *pas* sur la liste : une gravière de 800
mètres n’a d’eau libre dans aucune direction, et ce n’est pas une erreur. Une
version antérieure signalait justement ce genre de spots et ratait à la place
ceux qui étaient vraiment faux — une liste qui signale les mauvaises choses,
on arrête de la lire dès la deuxième fois.

Les corrections se font sur la carte : clique sur le spot, fais glisser
l’épingle dans l’eau ou clique dedans, **Appliquer**. Les coordonnées vont
dans `spots.yaml` (avec `verified: true`), l’ancienne géométrie du rivage est
supprimée et recalculée aussitôt — après quelques secondes, tu vois combien de
fetch le spot a désormais. Si les coordonnées sont finalement justes, **C’est bon** retire définitivement le spot de la liste (`geo_ok: true` dans le
catalogue).

Les commentaires de `spots.yaml` sont conservés : l’écriture se fait au niveau
du texte, pas par un aller-retour YAML.

### Catalogue — tous les spots en un coup d’œil

L’onglet **Catalogue**, en haut de chaque page, montre tous les spots que
Wingfoilscout connaît : recherche par nom, identifiant, région et remarque ;
filtres par pays, plan d’eau et caractéristique (non confirmés, avec
thermique, avec shorebreak, avec résultats Instagram, Instagram pas encore
recherché) ; tri par nom, pays, plan d’eau et distance au point de départ. Un
clic sur une ligne amène au spot sur la carte ; la carte montre toujours la
sélection en cours. Chaque spot a ses badges (confirmé, thermique,
shorebreak, accès, chiens) et des liens vers Windy, OpenStreetMap et
Instagram.

En bas de la page : **« Déjà dans le catalogue ? »** — saisis des coordonnées
ou un nom, et la page te dit si un spot proche figure déjà dans le catalogue
(jusqu’à 300 m : « pratiquement le même point », jusqu’à 3 km : « à proximité »). C’est ainsi que tu évites d’ajouter un spot deux fois.

**Tu peux aussi gérer le catalogue ici.** En dessous, **« Ajouter un nouveau spot »** : nom, coordonnées, plan d’eau, pays (vide = deviner), remarque,
commentaire — et, si tu veux, la géométrie du rivage est calculée tout de
suite. S’il existe déjà un spot à moins de 300 m, la page le signale et
n’ajoute le nouveau qu’avec « Ajouter quand même ». Chaque ligne propose trois
petites actions : **renommer** (le nom change, l’identifiant reste — la
géométrie du rivage, l’instantané Instagram et le banc d’essai y sont
rattachés), **déplacer** (une épingle apparaît sur la carte : fais-la glisser
ou clique sur la carte, puis « Appliquer » — comme sur la page « Vérifier les coordonnées », avec géométrie du rivage recalculée et `verified: true`) et
**supprimer** (avec confirmation ; le spot disparaît de `spots.yaml`,
`geometry.json` et `instagram.json`, et son bloc apparaît dans le journal
d’exécution au cas où c’était une erreur). Tout est écrit dans `spots.yaml` au
niveau du texte, et les commentaires restent ; pendant qu’une recherche ou un
calcul de géométrie est en cours, la page attend (409).
À côté, **proposer une correction** ouvre le
formulaire GitHub pour ce spot (voir [Proposer un spot à tous](#proposer-un-spot-à-tous)).

### Ton commentaire sur chaque spot

Partout où un spot apparaît, ton propre commentaire s’affiche avec lui et peut
être écrit sur place : dans le catalogue, sur chaque destination du rapport,
dans la popup de la carte, sur la page « Vérifier les coordonnées » et dans le
Bilan — et dès l’ajout d’un nouveau spot. « Écrire un commentaire » ouvre un
champ, « Enregistrer » l’écrit comme `comment` dans `spots.yaml` (plusieurs
lignes, jusqu’à 2000 caractères ; enregistrer un champ vide le supprime).
L’onglet Catalogue le trouve aussi par la recherche.

Le commentaire n’est pas la même chose que les `notes` : la remarque décrit le
spot (origine, règles, ce que dit la source), le commentaire est ton expérience
à toi — où te garer, où mettre à l’eau, comment c’était la dernière fois. Il ne
filtre rien et n’entre pas dans le score.

Une limite : le rapport est un fichier. Tant qu’il est affiché dans
l’interface (sous la recherche, ou via « ouvrir dans un nouvel onglet »), le
commentaire est enregistré dans le catalogue ; si tu ouvres `report.html`
directement comme fichier, le champ t’indique qu’il n’y a pas de programme
derrière. Un rapport montre l’état du catalogue au moment de sa recherche — un
nouveau commentaire apparaît immédiatement sur la page et dans le rapport
suivant.

### Bilan — la dernière prévision était-elle juste ?

L’onglet **Bilan** prend les dix meilleures destinations de la dernière
recherche et, pour les derniers jours, **aujourd’hui compris, jusqu’à l’heure en cours** (nombre au choix, de 1 à 14, 2 par défaut), met la prévision
archivée en regard du vent mesuré par la station météo la plus proche — heure
par heure, en courbe et en tableau, avec erreur moyenne, biais et taux de
réussite sur la direction par spot. La prévision passe par la même notation que dans le
rapport (modèle régional, `wind_factor`, thermique supposé) ; tu vois donc ce
que Wingfoilscout aurait dit, et ce qui s’est réellement passé.

Ce qu’il faut savoir figure aussi sur la page : la prévision archivée est
celle à l’échéance la plus courte (« aujourd’hui pour aujourd’hui », tirée de
l’archive d’Open-Meteo), pas celle d’il y a trois jours ; pour le jour en
cours, c’est la prévision de ce matin, issue de la requête en cours. Une
station mesure au-dessus de la terre, le spot est sur l’eau — quelques nœuds
d’écart sont normaux.

Les stations viennent du DWD (Allemagne), du KNMI et de Rijkswaterstaat
(Pays-Bas — Rijkswaterstaat mesure sur l’eau, sur des mâts de mesure et des
stations côtières), de GeoSphere (Autriche), du DMI (Danemark, depuis la
1.14.0) et de Météo-France (France) ; la recherche ignore les frontières, donc
un spot belge reçoit la station néerlandaise la plus proche. S’y ajoutent les
stations Windguru, si elles sont listées avec leur mot de passe API dans
`config.yaml` (`stationen: windguru:`, exemple dans `config.example.yaml`) —
sans mot de passe, Windguru ne fournit pas de mesures. **« Station jusqu’à … km »** (30 par défaut, 100 au maximum) fixe la distance maximale entre la
station et le spot ; on prend la plus proche qui a presque toutes les heures
jusqu’à maintenant (90 %), et si aucune n’en a autant, la plus proche qui en a
presque autant que la meilleure (depuis la 1.14.1 — avant, la plus proche
ayant la moindre valeur l’emportait, même si ses valeurs dataient
d’avant-hier). La station retenue est affichée avec sa distance à côté du
résultat, une station plus proche écartée avec « au lieu de … » — plus elle
est loin, moins elle en dit sur le spot.

Et jusqu’où la mesure s’approche de « maintenant » dépend du service, avec des
trous : le DWD a des heures contrôlées jusqu’à avant-hier et le jour en cours
à partir des valeurs à dix minutes — hier manque jusqu’à l’arrivée du fichier
quotidien suivant ; le KNMI va jusqu’à avant-hier (deux jours de retard — il
affiche alors « aucune valeur pour ces jours », et la station suivante prend
le relais) ; Rijkswaterstaat, GeoSphere et le DMI vont jusqu’à l’heure en
cours ; Météo-France jusqu’à tôt ce matin (le fichier quotidien paraît le
matin). Pour chaque spot, il est donc indiqué « Mesure disponible : … » avec
les heures qui ont une mesure ; sinon la courbe reste vide, et les
statistiques ne comptent que les heures communes aux deux. La comparaison
mensuelle fixe pour les changements de code, c’est le **banc d’essai**
([`BENCHMARK.md`](BENCHMARK.md)) ; le Bilan répond à la question « puis-je me fier au rapport que je viens de recevoir ? ».

**Comparaison des modèles** (depuis la 1.14.0) : sous chaque courbe, tu vois
quel modèle météo s’est le plus approché de la mesure sur ce spot — les
modèles globaux ICON, ECMWF, le modèle d’IA ECMWF-AIFS, GFS, Météo-France et
UKMO, et jusqu’à trois modèles régionaux qui couvrent le spot (ICON-D2,
AROME-HD, HARMONIE, CH1, ICON-2I, AROME-AT, DMI). Les modèles sont affichés
bruts, sans `wind_factor` ni thermique ; la « Note Wingfoilscout » inclut les
deux, sur une ligne à part. Le graphique ne montre d’abord que la mesure et,
en bande grise, la fourchette de tous les modèles (depuis la 1.15.0). Les
boutons en dessous activent des modèles individuels, la note Wingfoilscout et
**« Meilleur modèle jusqu’ici : … »** — le modèle qui, d’après la mémoire, a
été le plus juste sur ce spot (sinon sur l’ensemble des spots) ; trois
courbes au maximum à la fois. En bas de la page : le classement sur toutes
les destinations de ce bilan et la **mémoire** de toutes les vérifications
passées (`modellguete.json`, personnel, non versionné) — chaque jour compte une
fois, et une nouvelle vérification remplace un jour déjà présent. Au bout de
quelques semaines, elle te dit quel modèle voit juste où. Les modèles globaux
se changent dans `config.yaml` sous `rueckblick: modelle:`.

### Sur l’iPhone

Depuis la 1.17.0, l’interface est conçue pour les téléphones : une barre en
bas avec quatre entrées (Recherche, Destinations, Bilan, Carnet), le rapport
dans l’onglet « Destinations » avec un en-tête replié, la grille horaire et
les tableaux larges à faire défiler latéralement. Conçue et testée pour des
largeurs de 320 à 430 points — de l’iPhone SE au Pro Max.

**Sur le Wi-Fi, avec le Mac qui fait le travail.** Normalement, Wingfoilscout
n’écoute que sur 127.0.0.1. Pour un iPhone sur le même réseau :

```
python3 -m wingscout.webui --lan
```

ou double-clique sur **« Wingfoilscout fürs iPhone starten »**. Le terminal
affiche alors une adresse du type `http://192.168.178.25:8765/?k=Xf3k…` —
saisis-la dans Safari. La clé qu’elle contient est ton accès : sans elle, tout
autre appareil du réseau reçoit une erreur 401. Elle est enregistrée une fois
dans un cookie et reste valable jusqu’à l’arrêt de Wingfoilscout ; une fois le
cookie posé, l’adresse sans `?k=` suffit. La recherche tourne toujours sur le
Mac — l’iPhone ne fait qu’afficher les résultats et lancer des recherches.

**Sur l’écran d’accueil.** Dans Safari, « Partager » → « Sur l’écran d’accueil » : Wingfoilscout se lance alors comme une app, sans barre
d’adresse, avec sa propre icône.

**En route sans Mac.** Le rapport est un seul fichier HTML (`report.html` dans
le dossier Wingfoilscout). Envoyé sur l’iPhone par AirDrop, il s’y ouvre sans
réseau et sans le Mac — tout sauf la carte, qui charge ses tuiles depuis
Internet.

### Carnet — tes sessions étalonnent Wingfoilscout

L’onglet **Carnet** (depuis la 1.16.0) enregistre comment une session s’est
vraiment passée : spot, date, heure de début et de fin, wing, puissance
(sous-toilé / bien toilé / surtoilé), eau (plat / clapoteux / vagues) et une
note de 1 à 5. Une fois la session saisie, Wingfoilscout récupère, pour
exactement ces heures, ce qu’il aurait dit (le même calcul que dans le Bilan,
avec modèle régional, `wind_factor` et thermique), ce qu’ont dit les
différents modèles et — s’il y a une station météo à moins de 30 km — ce qui a
été mesuré. La session montre alors si Wingfoilscout aurait choisi une autre
wing ou prévu un autre état de l’eau. Si la mesure manque encore (le DWD ne livre la
veille qu’avec le fichier quotidien suivant), « Comparer à nouveau » la
récupère plus tard ; si une nouvelle comparaison trouve moins que l’ancienne
(pas de réseau), l’ancienne reste.

Plusieurs sessions donnent des **suggestions** — jamais appliquées
automatiquement :

- **Plage de vent par wing** (`config.yaml`) : sous-toilé à un vent que le
  quiver donne déjà comme adapté à cette wing, la limite basse remonte ;
  surtoilé à l’intérieur de la plage, la limite haute descend ; « bien toilé » en dehors, la plage s’élargit. Le vent de la session est la mesure
  si la station est à 15 km au plus, sinon la prévision de Wingfoilscout.
- **Facteur de vent par spot** (`spots.yaml`) : chaque session le cerne
  davantage — « bien toilé » signifie que le vent brut du modèle aux mêmes
  heures, multiplié par le facteur, était dans la plage de la wing utilisée.
  La suggestion est le facteur le plus proche avec lequel toutes les sessions
  du spot concordent (par pas de 0,05, entre 0,6 et 1,5). Les heures avec
  thermique supposé ne comptent pas ici.

Une suggestion demande au moins deux sessions qui vont dans le même sens ; si
des sessions se contredisent, il n’y en a pas. Si les mêmes sessions appuient
les deux types de suggestion, la page le signale — appliquer les deux
corrigerait deux fois le même constat. « Appliquer » ne modifie que cette
ligne-là ; les commentaires restent. Le carnet se trouve dans `tagebuch.json`
dans le dossier Wingfoilscout : personnel, non versionné, uniquement sur cet
ordinateur (et dans sa sauvegarde).

### Vents thermiques

Sur pas mal de spots, les modèles standard échouent. L’**Ora** sur le lac de
Garde, le **vent de la Maloja** en Engadine et le **Maestral** sur
l’Adriatique naissent de la différence de température entre la terre et
l’eau. Une maille de 7 à 25 km lisse justement les vallées et les côtes qui
créent cette circulation — le modèle affiche 5 kn, et sur place ça souffle à
18.

C’est pourquoi **71 spots du catalogue** contiennent des connaissances
enregistrées sur leur thermique : nom local du vent, mois, créneau horaire,
direction, force typique, fiabilité et **la source**. Wingfoilscout y suppose
un vent qu’aucun modèle n’affiche — mais seulement si la météo s’y prête :

- **Rayonnement depuis le lever du soleil.** Le thermique ne vit pas du
  soleil de l’heure en cours, mais de la chaleur que la matinée a emmagasinée
  dans le sol. D’où le rayonnement global cumulé plutôt que la couverture
  nuageuse — il pondère différemment les cirrus d’altitude et les couches
  basses de stratus, comme il se doit.
- **Vent contraire — et c’est là que ça devient intéressant.** Un vent de
  gradient offshore étouffe la brise dès 7 à 8 kn. Un vent contraire
  *faible*, en revanche, la **renforce** : il retient le front de brise sur
  la côte au lieu de le laisser filer vers l’intérieur des terres. La courbe
  de réponse culmine donc vers 3 kn de vent contraire et chute nettement
  au-delà. C’est exactement pour ça que le Maestral fonctionne — un faible
  vent de gradient de nord-ouest plus le thermique.
- **Flux synoptique bloquant.** Le vent de la Maloja ne vient « pratiquement jamais avec un flux synoptique de nord », même sous un ciel bleu. Ces
  exclusions sont enregistrées par spot dans le catalogue.
- **Heure de la journée** dans le créneau enregistré, avec montée en
  puissance et retombée.

Dans le rapport, les destinations à thermique apparaissent **dans une liste à part**, juste sous les trois meilleures — triées par potentiel thermique du
meilleur jour, pas par score global. Sans cette liste, elles se perdraient,
car le classement normal compte le vent du modèle, et c’est justement lui qui
est trop faible là-bas. La barre à côté de chacune est la **moyenne sur tout le créneau thermique** du rayonnement et du vent contraire, multipliée par la
fiabilité du spot tirée du catalogue ; la meilleure heure isolée figure dans
l’infobulle. Jusqu’à la 1.5.1, la barre montrait le maximum, et ça ne valait
rien : par une journée ensoleillée, chaque ingrédient finit par coller à un
moment donné, si bien que lors de l’exécution du 16 sept. 2026, les cinq
destinations étaient toutes entre 96 et 100 pour cent. Que la barre dépasse
désormais rarement 90 pour cent n’est pas un défaut — la fiabilité ne dépasse
nulle part 0,95 dans le catalogue, et pour la plupart des spots, c’est une
estimation volontairement prudente. Sur la carte, il y a pour cela une couche
**Vents thermiques** : un anneau orange autour de chaque spot dont le
thermique est enregistré. L’anneau est purement décoratif et n’intercepte
aucun clic — les détails s’ouvrent comme pour n’importe quel autre point.

En dessous vient **« Quand le thermique souffle »** : la même grille horaire,
mais colorée selon le potentiel thermique. Orange signifie du potentiel, pâle
signifie hors du créneau, et gris signifie : le créneau serait ouvert, mais
le vent de gradient ou le flux synoptique étouffe le thermique aujourd’hui. Un
cadre autour d’une heure signifie que l’hypothèse s’applique vraiment — le
vent du rapport vient du thermique et non du modèle. Contrairement à la liste
au-dessus, la grille ne dépend pas des destinations : un spot où les modèles
ne voient pas une seule heure navigable y figure quand même.

Ce que l’outil ne fait **pas** : inventer des thermiques. Il ne calcule que
sur les spots où le catalogue en signale un. Et là où aucune source ne donne
de force — le Chiemsee, le lac de Constance ou le lac de Thoune, par exemple —,
**aucune n’est supposée** ; le spot apparaît seulement comme candidat dans la
liste. Un vent supposé est toujours signalé comme hypothèse dans le rapport,
jamais comme valeur mesurée.

Désactivable via `thermal.enabled` dans la configuration, et atténuable via
`thermal.trust`.

### Modèles régionaux haute résolution

Les modèles globaux calculent sur une maille de 7 à 25 km. L’Ora naît dans
une vallée large de 2 km à son point le plus étroit ; le Maestral vit d’un
littoral qui, avec une maille de 25 km, devient un trait droit. Ce sont
justement ces circulations qui passent à travers la maille.

Wingfoilscout interroge donc en plus des modèles régionaux qui calculent à
**1 à 2,5 km** : `meteoswiss_icon_ch1` (Alpes), `italia_meteo_arpae_icon_2i`
(nord de l’Italie), `meteofrance_arome_france_hd`, `dwd_icon_d2`,
`knmi_harmonie_arome_netherlands`, `geosphere_arome_austria`,
`dmi_harmonie_arome_europe`. Là où l’un d’eux répond, il remplace le vent —
mais seulement pour les heures qu’il couvre : ces modèles portent à deux ou
trois jours, les globaux jusqu’à seize. Dans le rapport, chaque session
indique quel modèle l’a fournie.

Le modèle retenu se décide **d’abord selon le territoire, ensuite selon la résolution** :
pour un point en Italie, le modèle italien, même si le suisse a une maille plus
fine. Un modèle au bord de sa zone n’est pas la meilleure
source — là, le fournisseur manque de stations pour le vérifier. Chaque
session affiche l’écart **typique** avec le modèle grossier (« CH1 +5 kn ») —
la médiane sur les heures couvertes par le modèle fin. Le pic figure dans
l’infobulle. Jusqu’à la 1.5.0, le badge montrait le pic, et c’était
trompeur : il augmente avec la durée de la session plutôt qu’avec la qualité
du modèle, parce que plus il y a d’heures, plus il y a de chances d’en trouver
une favorable. Lors de la première vraie exécution, c’était mesurable — les
sessions jusqu’à huit heures avaient une médiane de 0 kn, celles de plus de
seize heures 6 kn.

Que la plupart des badges ne portent que le nom du modèle n’est donc pas un
bug mais le résultat : lors de l’exécution du 16 sept. 2026, seul **CH1 dans les Alpes** a apporté un gain régulier (médiane +5 kn, 86 % des sessions
au-dessus de 2 kn). **ICON-D2 sur les lacs plats de l’intérieur de l’Allemagne n’a rien apporté** — c’est le groupe témoin qui montre que le
calcul est juste : là où il n’y a pas de circulation à résoudre, une maille
plus fine ne gagne rien. Pour ICON-2I sur l’Adriatique, six sessions n’ont
pas suffi pour trancher.

Deux bizarreries rendent la chose plus pénible qu’il n’y paraît.
**Open-Meteo ne documente nulle part quel modèle couvre quel point** — la
doc dit seulement « Central Europe ». Et une requête pour un point hors du
domaine d’un modèle reçoit une réponse HTTP 400, pas des valeurs vides : dans
une requête groupée pour vingt coordonnées, un seul point inadapté fait tomber
tous les autres avec lui. Wingfoilscout coupe donc en deux les groupes
refusés jusqu’à isoler les intrus, et **mémorise le résultat par spot** dans
`cache/highres.json`. Cette petite danse n’a lieu qu’une fois, pas à chaque
exécution — et une fois de plus si les coordonnées du spot changent : depuis
la 1.7.0, chaque entrée du cache (extrait Overpass, zones protégées,
attribution du modèle, temps de trajet) porte les coordonnées auxquelles elle
s’applique, et ne s’applique à aucune autre.

Une fois à l’avance, pour que la première vraie exécution ne commence pas par
là :

```bash
python3 tools/highres_probe.py          # spots à thermique uniquement
python3 tools/highres_probe.py --alle   # tout le catalogue
```

Désactivable via la case **Modèles haute résolution** dans les Sources de
données, via `wind.highres` dans la configuration ou avec `--no-highres`.

### Quelle confiance accorder à la prévision ?

Si **Probabilité (ensemble)** est cochée, Wingfoilscout récupère en plus,
après le classement, l’ensemble ICON pour les meilleures destinations : la
même situation météo, calculée quarante fois avec des conditions initiales
légèrement décalées. Chaque session reçoit alors un badge — la part des
scénarios qui dépassent ton seuil de navigation dans le créneau, plus la
dispersion du décile inférieur au décile supérieur. L’infobulle montre la
médiane et la part qui atteint la zone de confort.

Cela ne remplace pas l’accord entre modèles, ça le complète : trois modèles te
disent si les services météo sont d’accord, quarante scénarios te disent à
quel point la situation est stable au départ. Il y a une limite — l’ensemble
tourne sur une maille plus grossière. À Brouwersdam, la requête tombe à 15 km
du spot, l’ICON déterministe à 3 km. C’est pourquoi il ne sert qu’à calculer
une probabilité et ne remplace jamais une valeur de vent.

Depuis la 1.5.0, ce chiffre n’est plus seulement affiché, il a son mot à dire.
Le score de la session est multiplié par lui, de façon atténuée :

    facteur = (1 − weight) + weight · part

Avec la valeur par défaut `weight: 0.5`, une session qu’aucun des quarante
scénarios ne soutient garde la moitié de son score — elle recule mais ne
disparaît pas. Multiplier sans atténuation viderait tout le rapport par une
situation météo incertaine, et il ne resterait plus rien, alors qu’il y a bien
quelque chose à décider. `weight: 0.0` rétablit le comportement des versions
jusqu’à la 1.4.3 : le badge est affiché et ne change rien. La requête couvre
les `ensemble.top` premières destinations (20 par défaut) ; ce qui est plus
bas n’est ni récompensé ni pénalisé et peut donc dépasser une destination
atténuée.

Il y a deux choses que l’ensemble ignore, et depuis la 1.7.0 on lui dit les
deux. D’abord, il ne connaît ni le modèle régional ni le `wind_factor` d’un
spot : on lui demande donc la valeur brute qui devient le seuil de navigation
après les deux corrections. Ensuite, il ne voit pas les thermiques — sur
l’Ora, il annonce 5 kn et 0 % de certitude, et jusqu’à la 1.6.1, cela divisait
par deux justement les sessions que l’outil avait spécialement corrigées. Pour
une session thermique, c’est désormais la **fiabilité du spot** tirée du
catalogue qui compte comme probabilité, avec le même facteur atténué ; le
badge l’indique (« Thermique supposé · fiable à 80 % »). Depuis, la vitesse du
vent elle-même vaut `typical_kn` multiplié par le potentiel — la fiabilité
n’est plus intégrée aux nœuds, où elle produisait une valeur qu’on n’observe
aucun jour.

### Heure locale

Tous les horaires sont en **heure locale du spot** : la Grèce et le Portugal
sont interrogés dans leur propre fuseau horaire, les Canaries et les Açores
dans le leur. Chaque colonne de la grille horaire montre la même heure locale,
le créneau thermique du catalogue compte comme heure locale, et « heure passée » lit la bonne horloge pour chaque spot. Jusqu’à la 1.6.1, tout était
en Europe/Berlin — une heure de décalage à Athènes.

### Jour, nuit et maintenant

Une session se déroule de jour et se termine avec le jour. Le lever et le
coucher du soleil viennent de la prévision ; s’ils manquent,
`wingscout/sonne.py` les calcule à partir de la latitude, de la longitude et
de la date. Si les deux sont disponibles, chaque exécution les compare et
écrit le plus grand écart dans le journal d’exécution — la formule de l’outil
se vérifie ainsi elle-même à chaque utilisation. Les heures déjà passées au
moment de l’exécution sont elles aussi écartées.

Jusqu’à la 1.4.3, rien de tout cela ne s’appliquait. Le contrôle était intégré
mais ne se déclenchait jamais : avec plusieurs modèles, le champ de la réponse
s’appelle `sunrise_dwd_icon_seamless` au lieu de `sunrise`. Résultat : trente
pour cent de toutes les heures de session tombaient entre 20 h 00 et 7 h 00,
et la plus longue « session » continue durait 59 heures.

### Lancer et quitter

L’interface tourne uniquement sur ton ordinateur (127.0.0.1:8765) et n’est pas
accessible de l’extérieur. Pour quitter, utilise le bouton **Quitter** en haut
à droite de la barre d’onglets, sur chaque page (sur téléphone, une petite
étiquette en haut à droite) — appuie deux fois, pour qu’il ne se déclenche pas
par accident en pleine exécution.

Si le port 8765 est déjà pris par un autre programme (un second serveur local,
par exemple une autre interface qui utilise le même port), Wingfoilscout passe
au port libre suivant et le signale dans le terminal — l’adresse est alors par
exemple `127.0.0.1:8766`, y compris celle pour l’iPhone. Si une interface
Wingfoilscout y tourne déjà, il n’en lance pas une deuxième ; celle qui tourne
est ouverte dans le navigateur à la place. Tu peux fixer le port explicitement
avec `python3 -m wingscout.webui --port 8790`.

Une recherche tourne dans le programme, pas dans la fenêtre du navigateur : tu
peux passer à d’autres onglets entre-temps — un point pulse alors sur l’onglet
« Recherche », et quand le rapport est prêt, « Destinations » reçoit un point
vert. Quand tu reviens à la recherche, elle affiche l’exécution en cours ou
terminée avec son heure. Une fois que tu as quitté, le programme dans la
fenêtre du terminal se termine aussi tout seul, et la fenêtre peut être fermée.
Ctrl+C dans le terminal fonctionne toujours aussi.

> Au premier double-clic, macOS peut signaler que le fichier provient d’un
> développeur non identifié. À partir de macOS 15 : Réglages Système →
> Confidentialité et sécurité → tout en bas « Ouvrir quand même » ; jusqu’à
> macOS 14, clic droit → Ouvrir → Ouvrir suffit. Ensuite, ça fonctionne normalement.
> Sinon, lance une fois dans le terminal : `xattr -d com.apple.quarantine "Wingfoilscout starten.command"`.

### Ligne de commande

```bash
python3 run.py                                   # 3 jours, 500 km, ouvre le rapport

python3 -m wingscout.cli --days 3 --radius 500   # mode spontané
python3 -m wingscout.cli --days 7 --radius 1000  # long week-end
python3 -m wingscout.cli --ab "2026-10-10 09:00" --days 2   # ce week-end seulement
python3 -m wingscout.cli --demo                  # données synthétiques, sans réseau
python3 -m wingscout.cli --days 2 --model icon_d2 --open
```

| Option | Signification |
|---|---|
| `--days N` | jours de prévision, 1–16 |
| `--ab HEURE` | début au lieu de maintenant (`2026-10-10 09:00`, `10.10.2026 09:00` ou seulement la date) ; les jours comptent à partir de là, 16 jours au plus |
| `--radius KM` | rayon de recherche en kilomètres de route (estimés à partir de la distance à vol d’oiseau) |
| `--max-drive H` | limite haute pour le trajet aller |
| `--min-hours H` | durée minimale pour qu’un bloc compte comme session |
| `--model NAME` | forcer un modèle Open-Meteo, p. ex. `icon_d2`, `icon_eu` |
| `--marine` | noter aussi la température de l’eau et le modèle de vagues (spots de mer et de lagune uniquement) ; les horaires de marée sont fournis même sans |
| `--no-geo` | ignorer la géométrie du rivage, n’utiliser que les secteurs du catalogue |
| `--nights N` | nuits prévues — exige N+1 jours exploitables d’affilée |
| `--demo` | données météo inventées, pour vérifier la mise en page et la logique |
| `--open` | ouvrir ensuite le rapport dans le navigateur |
| `--sprache de\|en\|fr\|es` | langue des messages et du rapport. Sans cette option : la langue choisie dans l’interface (`sprache.txt`), sinon celle du système (`LC_ALL`, `LC_MESSAGES`, `LANG`, puis les réglages de langue de macOS), sinon l’anglais. La variable d’environnement `WINGSCOUT_SPRACHE` l’emporte même sur `--sprache` |

`python3 -m wingscout.webui` écrit ses lignes de terminal selon la même règle,
simplement sans `--sprache`. Le texte `--help` de `wingscout.cli` est construit
avant ce choix : il ne suit que `WINGSCOUT_SPRACHE` ou la langue choisie dans
l’interface, sinon il est en allemand. Les fichiers à double-cliquer affichent
eux aussi leurs propres lignes dans les quatre langues (`tools/sprache.sh`) :
`WINGSCOUT_SPRACHE`, puis la langue choisie dans l’interface, puis les
réglages de langue de macOS, puis `LC_ALL`, `LC_MESSAGES`, `LANG`, sinon
l’anglais. Ce qu’ils lancent à leur tour est en partie encore en allemand : le
contrôle (`tools/check.sh`), la mise à jour (`tools/aktualisieren.sh`), le
banc d’essai et `build_geometry.py` affichent des messages en allemand, et
« Auf GitHub veröffentlichen » est entièrement en allemand.

## Ton quiver → ta plage de vent

Le quiver du fichier d’exemple (`config.example.yaml`), calibré pour 80 kg ;
le tien va dans `config.yaml`. Règle empirique : limite basse ≈ 65/surface,
limite haute ≈ 108/surface. **Ce sont des valeurs d’expérience, pas des mesures.**

| Wing | de | à |
|---|---|---|
| 6,5 m² | 10 kn | 17 kn |
| 5,0 m² | 13 kn | 22 kn |
| 4,2 m² | 15 kn | 26 kn |
| 3,5 m² | 19 kn | 31 kn |
| 2,5 m² | 26 kn | 43 kn |

Ensemble : **10–43 kn couverts sans trou.** Zone de confort pour la note :
14–28 kn. Si une session t’a semblé différente de la note du rapport —
saisis-la dans le **Carnet** ; à partir de deux sessions, il propose une autre
plage. Ou modifie directement les chiffres dans `config.yaml`, pas le code.

## Ce que le rapport évalue

Tout le chemin de décision — préfiltre, les sept vetos par heure, le score en
cinq composantes, sessions, fiabilité, ordre des destinations — est décrit
dans [`SCORING.md`](SCORING.md), avec les valeurs de configuration en regard —
et avec des figures sur la page
[« Comment Wingfoilscout calcule »](https://darkpiratego.github.io/wingfoilscout/bewertung.html)
(dans le dépôt : `docs/bewertung.html`).
En bref :

| Composante | Poids | Basé sur |
|---|---|---|
| Vitesse du vent | 34 % | wing adaptée, position plus ou moins centrale dans la plage de la wing, zone de confort |
| Direction du vent | 24 % | secteurs de `spots.yaml` |
| État de l’eau | 16 % | l’étiquette `water` du secteur × ton aversion au clapot |
| Météo | 14 % | température, pluie, CAPE |
| Taux de rafales | 12 % | rafale ÷ vent moyen |

### Temps de trajet : calculé par itinéraire, pas estimé

Avant, le trajet était la distance à vol d’oiseau multipliée par un facteur de
détour, à une vitesse moyenne supposée. Or c’est sur lui que repose la
décision la plus importante de tout l’outil — le trajet vaut-il le coup — et
c’est trop grossier pour ça : depuis Brouwersdam, la règle empirique estime
44 km et 31 minutes jusqu’à l’Oesterdam ; par la route, c’est 63 km et 61
minutes. En Zélande, il y a des digues et des bacs sur le chemin, dans les
Alpes des cols.

Désormais, Wingfoilscout interroge le serveur public OSRM via son service de
tables : un seul appel renvoie le temps de trajet du point de départ vers
toutes les destinations à la fois, et tout le catalogue tient dans une
requête qui prend une fraction de seconde. Les résultats sont stockés dans
`cache/routes.json`, avec le point de départ arrondi à un peu plus d’un
kilomètre — le serveur OSRM ne le reçoit lui aussi qu’à cette précision —, si
bien que des recherches répétées depuis le même endroit ne récupèrent plus
rien du tout.

Pour que l’estimation n’avale pas de destinations avant qu’elles soient
examinées, le préfiltre tourne avec une marge de 35 % sur le rayon et la
limite de temps de trajet ; tes vraies limites ne s’appliquent qu’après le
calcul d’itinéraire. Ne pas examiner une destination estimée de façon trop
pessimiste serait l’erreur la plus coûteuse.

Dans le rapport, « (estimé) » suit le temps de trajet si le calcul
d’itinéraire n’a pas été possible ; l’infobulle dit toujours d’où vient le
chiffre. Désactivable via la case dans les Sources de données —
`drive.detour_factor` de la configuration s’applique alors à nouveau.

### Emplacements pour la nuit avec chien

Sous chacune des meilleures destinations, il y a jusqu’à quatre emplacements
pour la nuit issus de Park4Night, triés par distance, type et note. **Les chiens doivent être explicitement acceptés** — ici, c’est un filtre strict,
contrairement au spot lui-même.

Deux choses à savoir. D’abord, le filtre animaux côté serveur de l’API n’est
pas fiable : il renvoie aussi des lieux sans aucune information sur les
services. Le filtrage se fait donc ici, à partir de l’entrée `animaux` du
lieu. Ensuite, une information manquante ne veut presque jamais dire
« chiens interdits », mais « personne ne l’a saisie ». Ces lieux sont quand
même écartés, mais comptés — le nombre apparaît sous la liste. Si une liste
courte sur une côte pleine de campings te surprend, voilà la raison, et le
lien Park4Night juste à côté montre alors tout.

Les parkings de jour, les aires de pique-nique et les simples points de
service (eau et vidange) sont exclus — on ne peut pas y passer la nuit. Le tri
convertit taille, distance et note en « kilomètres ressentis » : chaque
échelon vers un camping complet coûte un kilomètre et demi, une bonne note
rapporte jusqu’à un kilomètre d’avance. Ainsi, le petit emplacement gratuit
trois kilomètres plus loin l’emporte sur le grand camping au bord de l’eau,
mais la ferme à vingt kilomètres dans les terres, non.

L’API n’est pas officielle. Si elle tombe en panne, seule cette section
manque, rien d’autre. Désactivable via la case dans les Sources de données.

### Chiens et autorisations sur le spot

Deux champs du catalogue, `dogs` et `access`, apparaissent comme badge sur la
destination : chiens interdits, chiens en laisse, brevet de windsurf requis,
adhésion à un club, uniquement dans la zone, accès payant, explicitement
autorisé, autorisation incertaine, interdit. Si rien n’est affiché, les
sources ne disent rien — ce n’est pas la même chose que « autorisé ».

Cela ne filtre **rien**. Une interdiction des chiens sur la plage ne veut pas
dire que la journée est mauvaise ; ça veut dire que tu le sais à l’avance. Si
tu veux quand même masquer ces spots, tu trouveras deux cases pour ça sous
**Affiner la recherche → Eau** — toutes deux décochées par défaut.

### Shorebreak

Sur certains spots de mer, la vague déferle juste au bord — pour la mise à
l’eau et la sortie avec planche et wing, c’est le moment le moins agréable de
la journée. Le champ `shorebreak` du catalogue note cette observation, **à titre purement informatif** : il ne filtre rien et n’entre pas dans le score.

```yaml
  shorebreak:
    status: "yes"        # "yes" | "possible" | "no" | "unknown" — entre guillemets !
    note: "Offener Atlantikstrand; bei Swell bricht die Welle direkt am Ufer."
    source: "Spotwissen — unbelegt, bitte prüfen"
```

`"yes"` apparaît comme badge **Shorebreak** sur la destination, dans la popup
de la carte et dans le catalogue, `"possible"` comme **Shorebreak possible** ;
la remarque apparaît comme ligne sous l’en-tête de la destination et en
infobulle sur le badge. `"no"` et `"unknown"` restent muets — sur un lac,
« pas de shorebreak » ne serait que du bruit. Les guillemets sont
obligatoires : YAML lit un `yes` nu comme un booléen (le même piège qu’avec
`dogs: no`) ; le test du catalogue le signale.

Les entrées de la 1.9.0 (34 spots sur l’Atlantique, la mer du Nord et la
Manche) sont une première estimation fondée sur l’emplacement et
l’exposition, pas sur une observation directe — d’où
`source: Spotwissen — unbelegt` (« connaissance du spot — non vérifiée »). Si
tu connais un spot, corrige la ligne et indique la source.

### Marées — pleine mer et basse mer par spot

Depuis la 1.18.0, le rapport indique sur les spots à marée où en est la
marée, et peut en faire une règle si tu veux. La source est le niveau d’eau
modélisé `sea_level_height_msl` de l’API marine d’Open-Meteo, horaire sur une
maille de 8 km — marée et surcote due au vent confondues. Ce n’est **pas un annuaire des marées officiel** : par rapport à l’annuaire du marégraphe le
plus proche, les horaires diffèrent — de combien, ça n’a pas encore été
vérifié avec un annuaire (voir TODO) ; dans les baies et les estuaires,
attends-toi à plus que sur une côte ouverte. Pour « montante jusqu’à 15 h 00 », ça devrait suffire ; pour une traversée de l’estran à pied, non.

**Si la marée compte**, c’est le champ `tidal` qui le décide, spot par spot —
tu peux le régler dans le catalogue sous « Marées… », ou à la main dans
`spots.yaml` :

```yaml
  tidal: true      # la marée compte ici, même si le modèle montre peu de marnage
  tidal: false     # jamais — Baltique, Méditerranée, lagune derrière des écluses
                   # absent = automatique : mer ou lagune avec ≥ 0.5 m de marnage
```

L’automatique est la valeur par défaut pour tous les spots de mer et de
lagune : le modèle est interrogé, et s’il montre sur la période un marnage
moyen d’au moins 0,5 m entre pleine mer et basse mer, le spot compte comme
spot à marée (seuil `tide.auto_hub_min` dans la configuration). Attention aux
lagunes derrière des digues : la maille de 8 km voit souvent la mer du Nord
devant elles — le côté Grevelingen et le Spuikom à Ostende sont donc réglés
sur `false`.

**Ce que montre le rapport :** sur la destination, une ligne de marée avec
l’état actuel (« La mer monte · pleine mer à 14:50 (dans 1 h 40 min) » — la
phrase est calculée à l’ouverture du rapport et mise à jour chaque minute,
parce que le rapport est un fichier et que « maintenant » voulait dire autre
chose au moment de sa création), en dessous la pleine mer et la basse mer de
chaque jour à la minute près (interpolées à partir des valeurs horaires), le
marnage et la source. La ligne de session indique l’état au début de la
session et les pleines et basses mers qui y tombent ; l’infobulle de la
grille horaire, l’état pour cette heure ; la popup de la carte, la même ligne
que la destination. Les horaires sont en heure locale du spot, comme partout
dans le rapport.

**Une fenêtre de marée** fait de la marée une règle — seulement si tu en
définis une :

```yaml
  tide:
    fahrbar: hochwasser   # hochwasser | niedrigwasser | auflaufend | ablaufend
    stunden: 2            # ± heures autour de la pleine/basse mer (seulement avec hochwasser/niedrigwasser)
```

Les clés et les valeurs sont en allemand : `fahrbar` = praticable, `stunden` =
heures, `hochwasser` / `niedrigwasser` = pleine mer / basse mer, `auflaufend`
/ `ablaufend` = montante / descendante. Les heures hors de la fenêtre sont
écartées par un veto (« hors de la fenêtre de marée (PM ± 2 h) »), comme la
nuit ou une eau trop froide ; dans la grille, elles sont grises, et
l’infobulle donne la raison. `auflaufend` et `ablaufend` prennent toute la
demi-marée d’une étale à la suivante. Sans fenêtre, la marée ne change
**aucun score** — elle est alors purement informative. Quelle fenêtre
convient à un spot, seul le sait quelqu’un qui connaît le spot (un banc de
sable à marée basse, une plage de vase à marée haute) ; c’est pourquoi
Wingfoilscout ne livre aucune fenêtre, mais un réglage dans le catalogue :
« Marées… » à côté de renommer et déplacer, avec automatique / oui / non et le
choix de la fenêtre.

La case « Température de l’eau et modèle de vagues » (`--marine`) n’a plus
rien à voir avec la marée : les horaires de marée sont toujours fournis ; la
case décide seulement si la température de l’eau et la hauteur de vague du
modèle entrent dans la note. Les spots avec `tidal: false` ne sont pas du tout
interrogés sans la case.

### Liens pour chaque destination

Sous chaque destination, il y a six liens, dont les quatre premiers pointent
sur les coordonnées du spot : **Windy** (carte centrée sur le point — Windy
n’a pas de lien direct vers une position), **Itinéraire** (Google Maps, avec
le point de départ de la recherche comme origine, donc avec la distance depuis
là où tu es vraiment), **Vérifier sur la carte** (OpenStreetMap avec un
marqueur, pour vérifier les coordonnées) et **Park4Night** avec `lat`/`lng`
sur le spot, pour que les emplacements pour la nuit s’affichent tout de suite
dans la bonne zone. Plus **Instagram** et **Recherche Insta**, voir plus bas.

### Instagram

Si des gens font du wing sur un spot, ça se voit plus vite sur Instagram que
dans n’importe quel forum. Mais ça ne se vérifie pas automatiquement :
Instagram n’a pas de recherche publique sans connexion ni d’API gratuite qui
réponde à « y a-t-il des posts d’ici ? », et ses conditions d’utilisation
interdisent d’aspirer les pages. Wingfoilscout fait donc deux choses :

- **Deux liens par spot**, dans le rapport, dans la popup de la carte et dans
  le catalogue : **Instagram** mène à la page de lieu du spot (tous les posts
  qui y sont localisés) si elle est connue, sinon au hashtag formé à partir du
  nom (`#brouwersdam`) ; **Recherche Insta** est une recherche Google sur
  instagram.com avec le nom du spot et « wingfoil » — qui montre, même sans
  connexion, s’il y a des posts. Le hashtag peut être défini dans le catalogue
  (`instagram: "#tag"`), tout comme une adresse complète
  (`instagram: "https://www.instagram.com/…"`), par exemple la page de lieu ou
  un profil que tu as trouvé toi-même.
- **Un instantané** dans `instagram.json` : pour 100 spots, une recherche
  Google a été lancée le 18 sept. 2026
  (`site:instagram.com/explore/locations <Name>` pour la page de lieu,
  `site:instagram.com <Name> wingfoil` pour les résultats). Les résultats ont
  été gardés s’ils contiennent wing ou foil dans le titre, ou le nom du spot
  avec un mot lié aux sports nautiques ; les comptes apparus sur trois spots
  ou plus ont été retirés. Le résultat — 77 pages de lieu, 104 résultats —
  apparaît comme ligne **Instagram** sous la destination et dans le
  catalogue, avec la date et la mention « pas une preuve » : ce sont des
  résultats de recherche qui te disent où regarder, pas la preuve que des
  gens y font du wing. Pour les quelque 100 spots nommés restants, la
  recherche reste à faire (voir `TODO.md`) ; le lien **Recherche Insta** fait
  la même chose pour n’importe quel spot en un clic.

### Structure du rapport

D’abord les trois meilleures destinations (depuis la 2.3.0 avant la carte),
puis la carte, les thermiques, la grille horaire, toutes les autres
destinations, toutes les sessions en tableau, les spots écartés, et la
logique météo avec tes valeurs actuelles.

**Deux vues** (depuis la 1.20.0), à choisir en haut sous le titre :

- **Simple** — la réponse sans la machinerie derrière. Chaque destination est
  une section dépliable de deux lignes : rang, nom, trajet et heures sur
  l’eau, les badges qui décident d’y aller ou non (Le trajet vaut le coup,
  alertes officielles, thermique, marée, nombre de remarques) — et en dessous
  la meilleure session : quand, combien de vent, quelle wing, quelle
  orientation du vent. Toutes les sections plus bas n’affichent que leur titre
  et une phrase à leur sujet. Un clic sur une destination ou un titre ouvre
  exactement celui-ci.
- **Détaillée** — tout ouvert, comme le rapport se présentait jusqu’à la
  1.19.2 : commentaire, alertes en entier, marée, chaque session avec
  modèles, fetch et vagues, emplacements pour la nuit, liens, remarque du
  catalogue ; les sections dépliées. Seule « Autres destinations » reste
  fermée — personne ne veut 40 fiches d’un coup, pas même en vue détaillée.

Le navigateur retient le choix (`localStorage`), il s’applique donc à chaque
nouveau rapport jusqu’à ce que tu changes. Sans JavaScript, c’est Simple qui
s’applique ; les sections dépliables n’en ont pas besoin.

Le tableau des sessions se trie : un clic sur une colonne — Spot, Quand,
Durée, Vent, Orientation, Direction, Wing, Eau, Score — le trie, un second
clic inverse l’ordre. Les nombres pour lesquels plus vaut mieux (Durée, Vent,
Score) sont classés par ordre décroissant ; Orientation trie dans l’ordre
side-shore, side-on, onshore, offshore (les verdicts de secteur du catalogue
s’intercalent entre eux), Eau dans l’ordre plat, clapoteux, vagues.
**Orientation** est l’orientation du vent tirée de la géométrie du rivage ou
des secteurs, **Direction** la direction d’où vient le vent. Les 40 premières
lignes de l’ordre actuel sont affichées, « afficher les … » (avec le nombre de
sessions) lève la limite ; à valeurs égales, le score départage.

L’ordre suit ce pour quoi tu ouvres le rapport : où est-ce le mieux, où
cela se trouve-t-il, à quoi ressemble la semaine. Tu ne regardes le numéro 12 que
si les trois premiers ne tiennent pas leurs promesses.

### Grille horaire

Une ligne par spot, une colonne par heure, l’heure en haut. Deux façons de la
lire, à basculer avec l’interrupteur au-dessus :

- **Note** — l’heure vaut-elle le coup, oui ou non ? La couleur est le score
  tiré du vent, de la direction, des rafales et de la météo.
- **Nœuds** — de quelle wing as-tu besoin ? Rouge sous 11 kn, orange jusqu’à la limite
  basse de ta zone de confort, vert dans la zone, orange au-dessus, rouge à
  partir de la limite haute et **rouge foncé au-dessus de 30 kn**. Les heures
  de nuit et les heures exclues restent pâles, pour que le rythme de la
  journée reste lisible.

Le vert correspond toujours à la zone de confort de l’interface et bouge avec
elle quand tu la modifies là-bas. Les extrémités rouges sont dans
`config.yaml` sous `wind.red_below` (11), `wind.red_above` (26) et
`wind.dark_above` (30). Si une extrémité rouge tombait dans la zone de
confort — avec une zone de 14–28 et du rouge dès 26, ce serait le cas —, elle
s’efface au lieu de couper la zone en deux. Une heure ne peut donc jamais être
verte et rouge à la fois.

Le nom du spot mène à **Windy**, la distance à côté à l’**Itinéraire** —
« quel vent va-t-il faire ? » et « c’est loin ? » sont deux questions, et
chacune a sa propre cible.

Chaque case s’explique d’elle-même : sur ordinateur dans l’infobulle, et depuis
la 1.19.0 aussi d’un toucher ou d’un clic — sous la grille s’affiche alors ce
qu’il en était de cette heure (spot, heure, vent, note et la raison si elle
est exclue). Sur l’iPhone, c’est le seul moyen, car il n’y a pas d’infobulles.

### Carte

Le rapport s’ouvre sur une carte, et c’est une vue à part entière, pas une
illustration. Points : plein = destination avec une session (le top 3 plus
marqué), gris-bleu = dans le rayon mais sans vent, creux = écarté (raison dans
la popup).

Les interrupteurs en dessous permettent d’afficher ou de masquer chaque couche
séparément — sinon 277 points d’un coup ne font qu’un tapis de couleurs :

- **Top 3 / Session trouvée / Sans vent / Exclu**, chacun séparément
- **Emplacements pour la nuit avec chien** comme couche à part, avec nom,
  note, distance à l’eau et lien Park4Night
- **Un clic ouvre Windy au lieu des détails** — désactivé par défaut, car un
  clic sur un spot doit montrer ses détails. Si tu préfères sauter directement
  à la carte des vents, active-le. Même sans cet interrupteur, le **nom dans la popup** mène à Windy
- **Noms des spots trouvés** affichés en permanence ; au survol, chaque point
  montre de toute façon son nom
- **Rayon** en cercle pointillé
- **Zoom sur le top 3**, **Tout afficher**, **Plein écran** (Échap pour en
  sortir)

La popup d’un spot montre la meilleure session, la direction et la wing, le
trajet, la **bande horaire** dans la même échelle de couleurs que la grille
(survol pour l’heure et les nœuds), les coordonnées à copier et quatre liens :
Windy, Itinéraire, Park4Night et Vérifier sur la carte (OpenStreetMap) — plus
Instagram quand l’adresse du spot est connue. Un clic trace aussi la ligne à
vol d’oiseau jusqu’au point de départ.

La carte charge Leaflet depuis cdnjs et les tuiles depuis OpenStreetMap ; elle
a donc besoin d’Internet à l’ouverture. Sans réseau, un avis s’affiche à la
place de la carte et le reste continue de fonctionner.

### La météo en détail

| Grandeur | Champ Open-Meteo | Règle |
|---|---|---|
| Orage | `weather_code` | Code 95/96/99 → l’heure est écartée. Plus une ombre d’orage : jusqu’à 2 h avant et après, seulement 40 % du score, avec un avertissement dans la session |
| Potentiel orageux | `cape` | à partir de 1200 J/kg → 70 %, à partir de 2000 J/kg → 35 %, avec à chaque fois un avertissement |
| Pluie | `precipitation` | pas de pénalité jusqu’à 0,6 mm/h, puis baisse linéaire jusqu’à 3,0 mm/h, au-delà 20 % |
| Température de l’air | `temperature_2m` | hors de 7–35 °C, l’heure est écartée ; à moins de 3 °C d’une limite, 80 % |
| Température de l’eau | `sea_surface_temperature` | sous 7 °C, l’heure est écartée — seulement avec `--marine`, seulement mer et lagune |
| Marée | `sea_level_height_msl` (API marine) | pleine et basse mer sur les spots à marée ; seulement avec une fenêtre de marée dans le catalogue (`tide: fahrbar`), les heures en dehors sont écartées — sinon purement informatif |
| Lumière du jour | `sunrise` / `sunset`, sinon calculés | de 30 min après le lever du soleil à 30 min avant son coucher |
| Passé | heure de l’exécution | les heures déjà passées sont écartées |
| Couverture nuageuse | `cloud_cover` | récupérée, mais pas notée |

L’**ombre d’orage**, c’est là que l’outil va plus loin qu’un portail de
prévisions : le modèle ne signale que l’heure où il prévoit l’orage à ce point
de grille — sur l’eau, la fenêtre autour compte tout autant pour toi.

La logique météo figure aussi sous forme de tableau dans le rapport lui-même,
avec tes valeurs actuelles de `config.yaml` — les deux ne peuvent donc pas
diverger.

**Plans d’eau :** l’eau douce et l’eau salée sont toutes deux incluses
(`water.include_types`). Pour restreindre, retire des types de la liste.

**Exclusions strictes :** orage (code météo 95/96/99), température de l’air
hors de 7–35 °C, pas de wing adaptée, obscurité, on a pied partout, herbiers
denses, spot hors saison ou hors du rayon.

**Règle du temps de trajet :** ta règle « 6 h de route pour 2 h sur l’eau par jour » est enregistrée comme facteur 3 dans la configuration. Une destination
compte comme rentable (« Le trajet vaut le coup ») si
`drive time ≤ 3 × average hours on the water per day × (1 + 0.5 × nights)`,
plafonné à `drive.max_hours`. Au-delà, elle est marquée « Trajet limite », et
son rang est multiplié par 1 − 0,8 × dépassement ÷ temps autorisé — zéro à
125 % au-dessus du temps autorisé. Détails dans [`SCORING.md`](SCORING.md),
section 6.

## spots.yaml — le vrai trésor

Le catalogue est tenu à la main et **pas encore vérifié**. Chaque spot porte
`verified: false` jusqu’à ce que tu l’aies regardé. Le rapport donne un lien
vers une carte pour chaque spot — vérifier prend quelques secondes, et ensuite
le catalogue vaut plus que n’importe quel portail de prévisions. Ce qui arrive
par **fichier** via « Ajouter des spots » (GPX, KML, GeoJSON, CSV) est non
confirmé et apparaît sur la page « Vérifier les coordonnées » ; ce que tu
saisis toi-même ou copies depuis la carte compte comme regardé.
Sans type de plan d’eau, il reste `water_body: unknown` — le spot n’est alors
exclu par aucun filtre, et la géométrie du rivage dira plus tard dans quel
type d’eau il se trouve.

```yaml
- id: brouwersdam-grevelingen
  name: Brouwersdam – Grevelingenmeer (Innenseite)
  lat: 51.751
  lon: 3.836
  shallow: none | inshore | widespread
  seagrass: none | some | heavy
  season: [3,4,5,6,7,8,9,10,11]
  sectors:
    - {from: 200, to: 300, quality: best, water: flat}
  verified: false
```

`comment` est ton propre commentaire (voir plus haut), `notes` la description.
`from`/`to` est la direction **d’où vient le vent** (en degrés, 0 = nord).
Les secteurs peuvent passer par le nord (`from: 320, to: 40`). `quality` vaut
`best | good | ok | bad`, `water` vaut `flat | chop | wave`.

Un spot avec `disabled: true` reste dans le catalogue comme mémo, mais sort du
classement — comme Fehmarn/Gold, à cause des herbiers.

## Géométrie du rivage

La partie qui remplace le travail manuel.

```bash
python3 build_geometry.py            # une fois ; utilisable hors ligne ensuite
python3 build_geometry.py --only brouwersdam workum
python3 build_geometry.py --radius 25 --force
```

Pour chaque spot, la géométrie de l’eau est récupérée depuis OpenStreetMap
(côtes, lacs, lagunes, réservoirs), et le **fetch sur l’eau est mesuré dans 36 directions** — la première intersection d’un rayon avec une limite de l’eau.
Le résultat est stocké dans `geometry.json` et ne change plus ensuite.

Tout le reste découle de cette seule grandeur :

| Fetch au vent | Espace sous le vent | Orientation du vent | Évaluation |
|---|---|---|---|
| petit | grand | **offshore** | lisse, mais tu dérives vers le large → avertissement de sécurité ; avec `offshore_veto_km`, un veto dès qu’il y a autant d’eau sous le vent |
| grand | petit | **onshore** | vagues et shorebreak juste devant toi |
| les deux grands | les deux grands | **side-shore** | le meilleur cas |
| petit | petit | pas d’eau libre | les coordonnées sont fausses |

La hauteur de vague vient de la relation SPM limitée par le fetch
`H_s = 0.0016 · U · √(F/g)` — 20 kn sur 1 km donnent 12 cm, sur 40 km 1,05 m.
Une approximation d’ingénieur : elle suppose un vent constant et utilise U10 au
lieu du facteur de tension du vent. Elle suffit pour « lisse ou clapoteux » ;
elle ne remplace pas une prévision de vagues.

**Concrètement :** les spots sans secteurs saisis à la main — les
26 épingles de la liste de Jens Dee, par exemple — sont désormais notés
exactement comme tes spots de référence. L’orientation du vent et l’état de
l’eau viennent de la géométrie au lieu du travail manuel. Tes propres secteurs
dans `spots.yaml` ont la priorité ; avec
`geometry.prefer_manual_sectors: false`, c’est le calcul qui l’emporte.

Si un spot se trouve sur le parking plutôt que dans l’eau, le point de mesure
est automatiquement déplacé dans l’eau (les lacs par point-dans-polygone, les
côtes par la règle OSM « la terre à gauche, l’eau à droite »). Les spots
presque sans eau libre autour d’eux sont listés par `build_geometry.py` à la
fin — là, les coordonnées sont généralement fausses.

La première exécution sur 277 spots prend 10–30 minutes, presque entièrement
passées à attendre les serveurs Overpass. Chaque spot est enregistré
immédiatement, l’interrompre ne pose donc aucun problème.

## Ce qui manque encore

- **Géométrie du rivage pour le reste du catalogue** — le nombre de spots qui
  en manquent encore est affiché dans l’interface à côté du bouton
  « Calculer les manquants » ; environ un quart de minute par spot.
  `geometry.json` est versionné : après un calcul, il faut le committer,
  sinon le prochain clone recalcule tout depuis zéro.
- **Vérifier les coordonnées** : 122 spots viennent de listes importées et
  sont arrondis à trois ou quatre décimales, donc décalés jusqu’à environ un
  kilomètre. Le rapport les signale ; « Vérifier sur la carte » mène
  directement au point.
- **Profil de profondeur** d’EMODnet : mesurer la zone où l’on a pied au lieu
  de l’estimer. Les mers oui, les lacs intérieurs non — il n’y a pas de
  bathymétrie libre pour eux.

La liste qui fait foi est dans [`TODO.md`](TODO.md).

## Le banc d’essai — vérifier que tout est encore juste

Les tests vérifient hors ligne que le code fait ce qu’il doit. Le **banc d’essai** vérifie en ligne que l’ensemble tient toujours la route :
double-clique sur « Prüfstand » ou lance `python3 tools/pruefstand.py`. Pour
sept spots aux vents bien connus (Ora, vent de la Maloja, Breva…), il récupère
la prévision actuelle et vérifie la forme de la réponse, la note et si le
thermique apparaît là où il doit ; il fait passer un point du Jura souabe par
la géométrie du rivage et attend « pas d’eau dans un rayon de 3 km — l’épingle est-elle à terre ? » ; et pour dix spots
avec une station météo à portée, il compare la prévision archivée d’un mois
fixe avec la **mesure** — par modèle et pour Wingfoilscout dans son ensemble.
Les chiffres d’une bonne exécution sont enregistrés comme référence ; si une
modification ultérieure dégrade les choses, le banc d’essai le signale. Tout
le reste est dans
[`BENCHMARK.md`](BENCHMARK.md).

## Sources de données, licences et limites

Wingfoilscout lui-même est sous licence
[PolyForm Noncommercial 1.0.0](LICENSE) (depuis la 2.3.0 ; jusqu’à la 2.1.0,
c’était la licence MIT) : tu peux l’utiliser, le modifier et le transmettre
pour tout usage non commercial — usage personnel, loisir, étude et recherche,
et usage par des organismes caritatifs, d’enseignement, de recherche publique,
de sécurité publique ou de santé, de protection de l’environnement et par
l’administration —, à condition que les termes de la licence (ou leur adresse
web) et la ligne `Required Notice` l’accompagnent. Un usage commercial demande
une licence à part de DARK : à demander via une issue sur GitHub. Il n’y a
aucune garantie — pas non plus pour le vent. Les données sont soumises aux
conditions de leurs sources, voir ci-dessous ; `geometry.json` reste sous
l’ODbL d’OpenStreetMap.

Météo : [Open-Meteo](https://open-meteo.com), offre gratuite, non commerciale,
10 000 appels par jour ; les données sont sous licence CC BY 4.0. Une
exécution sur 25 spots coûte deux appels.

Ce qui se trouve dans le dépôt, et d’où ça vient :

- `spots.yaml` — tenu à la main. L’origine de chaque entrée est indiquée dans
  l’en-tête du fichier et dans le champ `source` : pages de spots Windfinder
  (coordonnées et rang de popularité), une liste Google Maps partagée,
  estimations propres (`verified: false`). Les noms et les coordonnées sont des
  faits ; les notes et les remarques sont un travail original.
- `geometry.json` — calculé à partir d’OpenStreetMap (côtes, surfaces d’eau,
  occupation du sol) : © les contributeurs d’OpenStreetMap,
  [ODbL 1.0](https://www.openstreetmap.org/copyright). Si tu transmets le
  fichier, transmets aussi cette mention.
- `instagram.json` — uniquement des adresses de pages Instagram publiques
  (écoles, clubs, pages de lieu), trouvées par recherche web ; aucun contenu,
  aucune image.
- `pruefstand/grundlinie.json` — chiffres dérivés (écart par modèle), pas de
  séries de mesures.

À l’exécution s’ajoutent les éléments suivants, dont aucun n’est stocké dans
le dépôt : mesures du DWD, du KNMI, de Rijkswaterstaat, de GeoSphere Austria,
du DMI et de Météo-France (données ouvertes, chacune aux conditions du
service), Windguru seulement avec le mot de passe API d’une station, temps de
trajet du serveur public OSRM, noms de lieux de Nominatim, géométrie du rivage
des serveurs Overpass, emplacements pour la nuit sous forme de liens vers
Park4Night, la carte avec [Leaflet](https://leafletjs.com) (BSD-2-Clause) et
les tuiles d’OpenStreetMap. Les règles d’utilisation des serveurs publics
s’appliquent ; Wingfoilscout met les réponses en cache pour ne pas les
interroger à chaque exécution.

Ce que le rapport ne sait **pas** : le niveau de marée officiel (seulement le
modèle à 8 km, voir « Marées »), la température de l’eau mesurée, les périodes
de fermeture, les réserves d’oiseaux, si le parking est payant, s’il y a
quelqu’un d’autre sur place en ce moment. Le rapport te dit où ça vaut le coup
d’aller voir — pas que tu dois y aller.

### Ce qui quitte ton ordinateur

Wingfoilscout n’a ni serveur propre ni compte. Il communique directement avec
les services publics ci-dessous, et chacun d’eux voit ton adresse IP. Ce
qu’ils reçoivent :

| Service | Reçoit |
|---|---|
| Open-Meteo (prévisions, état de la mer, ensemble, prévisions archivées) | coordonnées des spots |
| Overpass (géométrie du rivage) | coordonnées des spots |
| Park4Night (emplacements pour la nuit) | coordonnées des spots |
| Nominatim (nom de lieu et pays d’un spot que tu ajoutes) | coordonnées des spots |
| OSRM (temps de trajet) | ton point de départ arrondi à environ un kilomètre (deux décimales), plus les coordonnées des spots |
| MeteoAlarm (alertes météo) | seulement le pays |
| Stations météo — DWD, KNMI, Rijkswaterstaat, GeoSphere Austria, DMI, Météo-France (Bilan, Carnet, banc d’essai) | identifiants de station et plages de dates |
| Windguru (seulement si tu as configuré une station) | l’identifiant de la station et son mot de passe API, envoyés en HTTPS par POST |
| Serveur de tuiles OpenStreetMap (chaque carte) | les tuiles de la zone affichée par la carte |
| cdnjs (chaque carte) | la requête pour la bibliothèque Leaflet |

Ton nom, ton poids, ton matériel et ton carnet restent sur ton ordinateur. Tes
commentaires sur les spots sont écrits dans `spots.yaml` et ne voyagent qu’avec
le catalogue — si tu le publies, ils sont publics. Les liens du rapport et du
catalogue (Google Maps, Windy, Park4Night, Instagram…) n’envoient rien tant
que tu ne cliques pas dessus — le lien d’itinéraire Google Maps transmet alors
ton point de départ tel qu’il a servi pour la recherche.
**Proposer à tous** et **proposer une correction** ouvrent GitHub ;
ce qu’ils remplissent (nom, coordonnées, remarque) passe dans l’adresse.
Ce que tu y envoies est public, sous ton nom GitHub.

## Développement

[`CONTRIBUTING.md`](CONTRIBUTING.md) décrit comment deux personnes y
travaillent sans se marcher dessus ; [`DEVELOPMENT.md`](DEVELOPMENT.md) couvre
la structure, les tests et les règles Git ; [`SECURITY.md`](SECURITY.md)
l’audit du 13 sept. 2026 avec constats et correctifs ; [`TODO.md`](TODO.md)
est la liste de référence des points ouverts ; [`CHANGELOG.md`](CHANGELOG.md)
consigne ce qui a changé et quand.

Contrôle avant chaque commit : `tools/check.sh` ou « Tests ausführen » dans le
Finder — environ 700 tests, sans paquets tiers, une à deux minutes. Après un
nouveau clone, lance une fois `tools/install-hooks.sh` pour que le contrôle
tourne avant chaque commit.

```
wingscout/          code du programme (cli, score, report, webui, geometry, sources/)
.github/            contrôle sur GitHub, CODEOWNERS, modèle de PR
tests/              tests, unittest pur
tools/              contrôle, hooks, publication et mise à jour
import/             scripts d’import ponctuels et listes brutes
spots.yaml          le catalogue — le vrai trésor
config.example.yaml tous les seuils et règles, commentés — fichier d’exemple
config.yaml         ta version personnelle, non versionnée
geometry.json       géométrie du rivage calculée, dérivée mais versionnée
```
