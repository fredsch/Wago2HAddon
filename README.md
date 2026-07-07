# Wago2HAddon

Passerelle **Home Assistant** ↔ automate **Wago 750-881** équipé du programme
**Codesys Calaos**. L'intégration parle le protocole d'origine de Calaos (Modbus/TCP
+ UDP 4646), sans MQTT ni Docker, et expose vos entrées/sorties comme des entités
natives Home Assistant.

> **Terminologie.** HACS distribue des *intégrations personnalisées* (du code Python
> exécuté dans Home Assistant), pas des *add-ons* au sens du Superviseur (conteneurs
> Docker). Wago2HAddon est donc livré comme une **intégration personnalisée
> installable via HACS** : c'est la forme correcte pour maintenir le heartbeat
> permanent et créer des entités natives. Le nom « Wago2HAddon » est conservé.

## Ce que fait l'intégration

- **Entrées TOR** (bornes type 750-1405 / 750-430) : clic simple, **double-clic**,
  **triple-clic** et **clic long**, décodés côté passerelle à partir des fronts bruts
  envoyés par l'automate. Chaque entrée devient une entité `event` (+ un
  `binary_sensor` reflétant l'état brut de la ligne).
- **Sorties TOR** (bornes type 750-1504 / 750-430) : relais, luminaires, pompes…
  exposés en `light` (si repérés comme éclairage) ou `switch` (relais/pompe).
- **Volets** (`WOVoletSmart`) : entité `cover` avec **position estimée** à partir des
  **temps de montée/descente en secondes** (le programme interne étant suspendu, la
  logique de position vit dans la passerelle).
- **DALI** (borne 750-641) : éclairages simples (`light` avec variation) ou **RGB**
  (`light` couleur), via `WAGO_DALI_SET` / `WAGO_DALI_GET`.
- **Analogique / température** (borne 750-640 + sondes PT100/PT1000) : entité `sensor`
  **relevée toutes les 2 minutes** par défaut (intervalle réglable), conversion
  signée ÷10 pour la température.
- **Suspension du programme interne** : tant que la passerelle tourne, un *heartbeat*
  périodique maintient l'automate en « mode serveur », ce qui **suspend** son
  programme autonome (`ManageOutput`). Voir plus bas.
- **Diagnostic de l'automate** : deux entités de diagnostic sont créées automatiquement
  pour chaque automate — un `binary_sensor` de **connectivité En ligne/Hors ligne**
  (sondé en Modbus toutes les 30 s) et un `sensor` affichant la **version du programme
  Calaos** installé sur le Wago (commande `WAGO_GET_VERSION`). La version apparaît aussi
  directement sur la page de l'appareil (champ « Version logicielle »).

## Installation via HACS

1. HACS → menu ⋮ → **Dépôts personnalisés** → ajoutez l'URL de ce dépôt, catégorie
   **Integration**.
2. Installez **Wago2HAddon**, puis redémarrez Home Assistant.
3. **Paramètres → Appareils et services → Ajouter une intégration → Wago2HAddon**.

## Configuration

| Champ | Rôle | Défaut |
|-------|------|--------|
| Adresse IP de l'automate | IP du Wago | — |
| Port Modbus/TCP | Modbus | 502 |
| Port UDP Calaos | Heartbeat / DALI / entrées | 4646 |
| Chemin du `io.xml` | Import automatique des entités | (optionnel) |
| IP locale | Destinataire des notifications d'entrées | auto-détectée |
| Intervalle analogique/température | Cadence de lecture | 120 s |
| Intervalle heartbeat | Cadence du heartbeat | 10 s |
| Famille 750-8xx | Décalage d'adresse des sorties (+4096) | vrai |
| Délai max entre clics | Fenêtre double/triple | 350 ms |
| Seuil clic long | Durée d'un appui long | 500 ms |

### Import du fichier Calaos `io.xml`

Le plus simple est de laisser l'intégration lire votre configuration Calaos existante.
Copiez votre `io.xml` (par ex. `io_20260703.xml`) dans le dossier `/config` de Home
Assistant et indiquez son chemin (ex. `/config/io_20260703.xml`). L'intégration ne
retient que les entités **Wago** de l'automate configuré (les MQTT, scénarios,
caméras, minuteries internes de Calaos sont ignorés). Vos 24 pièces et l'ensemble des
entités sont recréés automatiquement, nommés `Pièce - Nom`.

Pour recharger après modification du fichier : **⋮ → Recharger** sur l'intégration.

## Mécanisme de suspension du programme interne

Le firmware Codesys de Calaos possède une variable `HEARTBEAT` :

- à la réception d'un `WAGO_HEARTBEAT` (UDP 4646), un minuteur de 30 s est réarmé ;
- tant qu'il ne déborde pas, `HEARTBEAT = TRUE` et le bloc `ManageOutput` (télérupteurs,
  volets, DALI en autonome) **n'est pas exécuté** : l'automate est piloté par la
  passerelle ;
- si plus aucun heartbeat n'arrive pendant 30 s, `HEARTBEAT = FALSE` : l'automate
  repasse en mode **autonome** (sécurité).

Wago2HAddon envoie `WAGO_SET_SERVER_IP <ip>` puis `WAGO_HEARTBEAT` toutes les 10 s.
Quand vous arrêtez l'intégration, l'automate reprend donc automatiquement sa logique
interne au bout de 30 s.

## Correspondance des entités

| Type Calaos | Entité HA | Détails |
|-------------|-----------|---------|
| `WIDigitalBP` | `event` + `binary_sensor` | clic simple |
| `WIDigitalTriple` | `event` + `binary_sensor` | simple / double / triple |
| `WIDigitalLong` | `event` + `binary_sensor` | simple / long |
| `WODigital` (light) | `light` | marche/arrêt |
| `WODigital` (relais) | `switch` | relais / pompe |
| `WOVolet` / `WOVoletSmart` | `cover` | position par temps |
| `WODali` | `light` | variation 0-100 % |
| `WODaliRVB` | `light` | couleur RGB |
| `WITemp` | `sensor` | température °C (÷10) |
| `WIAnalog` | `sensor` | valeur analogique |

## Carte des adresses (identique à `calaos_base`)

Communication sur **deux canaux** :

**Modbus/TCP (port 502, esclave 1)**

| Opération | Fonction | Adresse |
|-----------|----------|---------|
| Lire une entrée TOR | FC1 (read coils) | `var` |
| Écrire une sortie TOR | FC5 (force coil) | `var + 4096` (famille 750-8xx) |
| Relire une sortie TOR | FC1 (read coils) | `var + 512` (repli `var`) |
| Lire un registre analogique | FC3 (read holding) | `var` (température = signé ÷10) |

**UDP (port 4646)**

| Message | Sens | Format |
|---------|------|--------|
| Heartbeat | HA → PLC | `WAGO_SET_SERVER_IP <ip>` puis `WAGO_HEARTBEAT` |
| Changement d'entrée | PLC → HA | `WAGO INT <var> <0\|1>` |
| Commande DALI | HA → PLC | `WAGO_DALI_SET <line> <group> <address> <dimm%> <fade>` |
| Lecture DALI | HA ↔ PLC | `WAGO_DALI_GET <line> <address>` → `WAGO_DALI_GET <0\|1> <dimm%>` |
| Version du programme | HA ↔ PLC | `WAGO_GET_VERSION` → `WAGO_GET_VERSION <H>.<L> 750-841` |

## Notes techniques

- Client Modbus/TCP **autonome** (pas de dépendance `pymodbus`, donc aucun conflit de
  version avec la copie embarquée de Home Assistant).
- `iot_class: local_push` : les entrées arrivent en temps réel par UDP ; seuls les
  capteurs analogiques sont interrogés périodiquement.
- L'état DALI est optimiste, rafraîchi en tâche de fond via `WAGO_DALI_GET`.

## Licence

GPLv3, comme le projet Calaos dont le protocole est ici ré-implémenté.
