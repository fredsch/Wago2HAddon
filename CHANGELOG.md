# Journal des modifications

Toutes les évolutions notables de Wago2HAddon sont consignées ici.
Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/)
et le projet suit un versionnage sémantique.

## [1.0.5] - 2026-08-24

### Modifié
- Version de maintenance : montée de version, sans changement fonctionnel depuis
  la 1.0.4.

## [1.0.4] - 2026-08-24

### Corrigé
- **Lumières DALL qui repassaient à « éteint » ~1-2 min après l'allumage.**
  L'état DALI était relu périodiquement via `WAGO_DALI_GET`, or cette relecture
  renvoie « éteint » (la requête est peu fiable, et impossible pour du DMX en
  adresse ≥ 100), ce qui écrasait l'état réel. Conformément à Calaos, l'état DALI
  n'est plus interrogé en boucle : il est lu **une seule fois au démarrage** (et
  uniquement pour les vraies adresses DALI 1-64), puis suivi de façon **optimiste**.
  Comme le programme interne de l'automate est suspendu, une lumière DALI ne peut
  changer que depuis Home Assistant : l'état optimiste est donc exact.

## [1.0.3] - 2026-08-24

### Corrigé
- **Entrées instables : des clics étaient perdus par intermittence** (issue #2).
  Le socket d'écoute UDP (port 4646) était ouvert avec `SO_REUSEPORT` ; sous Linux,
  le noyau répartit alors les datagrammes entrants entre tous les sockets liés au
  même port. Après un rechargement, une mise à jour ou un redémarrage, un ancien
  socket restait parfois lié et « volait » une partie des paquets `WAGO INT`, qui
  étaient silencieusement perdus. Le socket est désormais **exclusif** : tous les
  paquets d'entrée arrivent à la seule instance qui écoute.
- Fermeture propre du socket UDP au déchargement (attente de sa libération réelle)
  et ré-essai du binding au démarrage, pour qu'un rechargement ne crée jamais deux
  sockets en concurrence sur le port.

### Ajouté
- Émission d'un **événement de bus** `wago2haddon_event` à chaque action décodée
  (clic simple/double/triple, appui long), en plus de l'entité `event`. Un
  déclencheur `event` sur cet événement est totalement fiable (jamais dédupliqué)
  et constitue une alternative robuste pour les automatisations.
- Traitement défensif de plusieurs messages par datagramme (aucun message n'est
  ignoré si l'automate venait à en grouper).
- Annulation propre des minuteries du décodeur d'entrées à la suppression d'une
  entité (évite qu'un événement se déclenche après un rechargement).

## [1.0.2]

### Ajouté
- **Version du programme Calaos** installé sur l'automate, lue via la commande UDP
  `WAGO_GET_VERSION` : affichée sur la page de l'appareil (champ « Version
  logicielle ») et exposée comme capteur de diagnostic, rafraîchie à chaque
  reconnexion.
- **Capteur de connectivité En ligne / Hors ligne** (`binary_sensor`, classe
  *connectivité*), basé sur une sonde Modbus fiable exécutée périodiquement.

## [1.0.1]

### Corrigé
- Erreur au démarrage `ModuleNotFoundError: No module named
  'homeassistant.helpers.device_info'` (qui se manifestait par le message trompeur
  « Platform wago2haddon.light not found »). `DeviceInfo` est désormais importé
  depuis `homeassistant.helpers.device_registry`.

## [1.0.0]

### Ajouté
- Première version : passerelle Home Assistant ↔ automate Wago 750-881 sous
  programme Codesys Calaos, via Modbus/TCP (502) et UDP (4646).
- **Entrées** TOR décodées en clic simple / double / triple / appui long
  (entités `event` + `binary_sensor`).
- **Sorties** TOR en `light` ou `switch` (relais, luminaires, pompes).
- **Volets** (`WOVoletSmart`) en `cover` avec position estimée à partir des temps
  de montée/descente en secondes.
- **DALI** simple (variation) et **RGB** (couleur) via `WAGO_DALI_SET`.
- **Température / analogique** (PT100/PT1000) en `sensor`, relevé périodique
  (2 min par défaut).
- **Suspension du programme interne** de l'automate tant que la passerelle tourne,
  au moyen d'un heartbeat périodique (mode serveur).
- **Import** de la configuration Calaos `io.xml` pour créer automatiquement toutes
  les entités.

[1.0.5]: https://github.com/fredsch/Wago2HAddon/releases/tag/1.0.5
[1.0.4]: https://github.com/fredsch/Wago2HAddon/releases/tag/1.0.4
[1.0.3]: https://github.com/fredsch/Wago2HAddon/releases/tag/1.0.3
[1.0.2]: https://github.com/fredsch/Wago2HAddon/releases/tag/1.0.2
[1.0.1]: https://github.com/fredsch/Wago2HAddon/releases/tag/1.0.1
[1.0.0]: https://github.com/fredsch/Wago2HAddon/releases/tag/1.0.0
