# MongoDB Sharded Cluster — E-commerce Application

> **Projet académique** — Université Abdelmalek Essaadi, ENSAH Al Hoceima  
> Module : Administration des Bases de Données Avancées  
> Encadrante : Prof. EL MORABIT Yasmina  
> Réalisé par : AALILOUCH Fatima Zohra · ABAKOUY Asmae · SALIHI Zineb

---

## Description

Application web e-commerce connectée à un **cluster MongoDB shardé** déployé sur trois machines physiques reliées via un VPN (ZeroTier). L'application permet la **recherche d'images similaires** dans un catalogue de produits (vêtements, accessoires…) en exploitant des features vectorielles extraites par un modèle **VGG16** et comparées par similarité cosinus.
Le cluster gère plus de **486 000 documents** et environ **44 436 images produits**, répartis sur deux shards replica sets pour assurer scalabilité, haute disponibilité et tolérance aux pannes.

---

## Architecture technique

```
Data Source (Amazon Dataset)
        │
        ▼
┌───────────────────────────────────────────┐
│         Cluster MongoDB Shardé            │
│                                           │
│   ┌──────────────────────────────────┐    │
│   │       mongos (Routeur)           │    │
│   │  Machine 1: port 27017           │    │
│   │  Machine 2: port 27021           │    │
│   └────────────┬─────────────────────┘    │
│                │                          │
│   ┌────────────┼────────────┐             │
│   ▼            ▼            ▼             │
│  Shard 1    Shard 2    Config Servers     │
│ (port 27018)(port 27020)  (port 27019)    │
│  3 nœuds    3 nœuds      3 nœuds          │
│  ReplicaSet ReplicaSet  ReplicaSet        │
└───────────────────────────────────────────┘
        │
        ▼ Driver PyMongo
┌───────────────────┐
│   Application Web │
│  Backend: Flask   │
│  Frontend: HTML   │
└───────────────────┘

Infrastructure Réseau : ZeroTier VPN
  Machine 1 : 10.223.141.71
  Machine 2 : 10.223.141.112
  Machine 3 : 10.223.141.104
```

**Shard key** : `masterCategory` (range sharding)  
**Collection shardée** : `amazondb.products`  
**Distribution** : ~47.5% shard1 (92 371 docs) · ~52.5% shard2 (394 051 docs)

---

## Structure du projet

```
MongoDB_Project/
├── app.py                        # Application Flask principale
├── connexion_mongodb.py          # Connexion simple à MongoDB
├── model.py                      # Modèle ResNet50 (classification)
├── dataset/
│   └── styles.csv                # Dataset Amazon (44 436 produits)
└── static/
    └── images/
        └── products/
            ├── 10826.jpg         # (3 images d'exemple incluses)
            ├── 10827.jpg         # Le dataset complet contient 44 436 images
            └── 10828.jpg         # À télécharger séparément (voir ci-dessous)
```

> **Note images** : Le dossier `static/images/products/` ne contient que 3 images d'exemple dans ce dépôt. Le dataset complet avec les 44 436 images est disponible sur [Kaggle — Fashion Product Images](https://www.kaggle.com/datasets/paramaggarwal/fashion-product-images-dataset). Placez toutes les images dans `static/images/products/`.

---

## Prérequis

- Python 3.8+
- MongoDB 8.x (installé sur les 3 machines)
- MongoDB Shell (`mongosh`) 2.x
- ZeroTier (pour le réseau multi-machines)
- Les dépendances Python listées ci-dessous

---

## Installation et déploiement

### Étape 1 — Réseau entre les machines (ZeroTier)

Les trois machines étant situées dans des endroits différents, ZeroTier crée un réseau privé virtuel commun.

**1.1 Créer un réseau sur [my.zerotier.com](https://my.zerotier.com)**  
Un membre du groupe crée le réseau et récupère l'`ID_du_réseau`.

**1.2 Installer ZeroTier sur chaque machine** : [zerotier.com/download](https://www.zerotier.com/download/)

**1.3 Rejoindre le réseau sur chaque machine :**
```bash
zerotier-cli join <ID_du_réseau>
```

**1.4 Autoriser chaque machine** dans l'interface ZeroTier (onglet "Member Devices" → cocher "Authorized").

**1.5 Vérifier la connexion :**
```bash
zerotier-cli listnetworks
ping 10.223.141.112   # Adapter selon les IPs attribuées
```

---

### Étape 2 — Préparer les dossiers sur chaque machine

```bash
mkdir D:\mongodb\data\configdb
mkdir D:\mongodb\data\shard1
mkdir D:\mongodb\data\shard2
mkdir D:\mongodb\log
```

---

### Étape 3 — Config Server Replica Set

Lancer sur **chaque machine** (adapter l'IP si nécessaire) :
```bash
mongod --configsvr --replSet cfgReplSet --port 27019 \
       --dbpath "D:\mongodb\data\configdb" --bind_ip 0.0.0.0
```

Initialiser le replica set (depuis **une seule machine**) :
```js
mongosh --port 27019

rs.initiate({
  _id: "cfgReplSet",
  configsvr: true,
  members: [
    { _id: 0, host: "10.223.141.71:27019" },
    { _id: 1, host: "10.223.141.112:27019" },
    { _id: 2, host: "10.223.141.104:27019" }
  ]
})
```

---

### Étape 4 — Shard 1 Replica Set

Lancer sur **chaque machine** :
```bash
mongod --shardsvr --replSet shard1ReplSet --port 27018 \
       --dbpath "D:\mongodb\data\shard1" --bind_ip 0.0.0.0
```

Initialiser (depuis **une seule machine**) :
```js
mongosh --port 27018

rs.initiate({
  _id: "shard1ReplSet",
  members: [
    { _id: 0, host: "10.223.141.71:27018" },
    { _id: 1, host: "10.223.141.112:27018" },
    { _id: 2, host: "10.223.141.104:27018" }
  ]
})
```

---

### Étape 5 — Shard 2 Replica Set

Lancer sur **chaque machine** :
```bash
mongod --shardsvr --replSet shard2ReplSet --port 27020 \
       --dbpath "D:\mongodb\data\shard2" --bind_ip 0.0.0.0
```

Initialiser (depuis **une seule machine**) :
```js
mongosh --port 27020

rs.initiate({
  _id: "shard2ReplSet",
  members: [
    { _id: 0, host: "10.223.141.71:27020" },
    { _id: 1, host: "10.223.141.112:27020" },
    { _id: 2, host: "10.223.141.104:27020" }
  ]
})
```

---

### Étape 6 — Routeur Mongos

**Machine 1 (port 27017) :**
```bash
mongos --configdb cfgReplSet/10.223.141.71:27019,10.223.141.104:27019,10.223.141.112:27019 \
       --port 27017
```

**Machine 2 (port 27021) :**
```bash
mongos --configdb cfgReplSet/10.223.141.71:27019,10.223.141.104:27019,10.223.141.112:27019 \
       --port 27021
```

---

### Étape 7 — Ajouter les shards au cluster

Se connecter au routeur Mongos :
```bash
mongosh --port 27017
```

Ajouter les deux shards :
```js
sh.addShard("shard1ReplSet/10.223.141.71:27018,10.223.141.112:27018,10.223.141.104:27018")
sh.addShard("shard2ReplSet/10.223.141.71:27020,10.223.141.112:27020,10.223.141.104:27020")

// Vérifier que les shards sont bien enregistrés
sh.status()
```

---

### Étape 8 — Activer le sharding et importer les données

```js
use amazondb
db.createCollection("products")
db.products.createIndex({ "masterCategory": 1 })
sh.enableSharding("amazondb")
sh.shardCollection("amazondb.products", { masterCategory: 1 })
```

Importer les données avec le script Python (à adapter selon votre chemin) :
```bash
python import_data.py
```

Vérifier la distribution :
```js
db.products.getShardDistribution()
sh.isBalancerRunning()
db.products.stats().sharded   // doit retourner true
```

---

### Étape 9 — Lancer l'application web

Installer les dépendances Python :
```bash
pip install flask pymongo tensorflow keras scikit-learn numpy tqdm
```

Lancer l'application :
```bash
python app.py
```

L'application est accessible sur `http://localhost:5000`

---

## 🔌 Routes disponibles

| Route | Méthode | Description |
|---|---|---|
| `/` | GET | Interface principale |
| `/upload` | POST | Upload image → retourne produits similaires |
| `/status` | GET | Statistiques de la base de données |
| `/test-connection` | GET | Test de connexion au cluster MongoDB |

---

## Tests de requêtes

```js
// Compter tous les documents
use amazondb
db.products.count()            // → 486 422

// Voir un exemple de document
db.products.findOne()

// Requête filtrée par catégorie (utilise le sharding)
db.products.find({ masterCategory: "Apparel" }).explain("executionStats")

// Vérifier la distribution par shard
db.products.getShardDistribution()
```

---

## Résultats obtenus

| Métrique | Valeur |
|---|---|
| Documents total | 486 422 |
| Shard 1 (shard1ReplSet) | 92 371 docs — 378.66 MiB (~47.5%) |
| Shard 2 (shard2ReplSet) | 394 051 docs — 418.16 MiB (~52.5%) |
| Cluster total | 796.83 MiB |
| Auto-split | Activé |
| Balancer | Activé |

---

## Stack technique

| Composant | Technologie |
|---|---|
| Base de données | MongoDB 8.2.1 (Sharded Cluster) |
| Réseau multi-machines | ZeroTier VPN |
| Backend | Python / Flask |
| Extraction de features | VGG16 (Keras / TensorFlow) |
| Similarité | Cosine Similarity (scikit-learn) |
| Driver MongoDB | PyMongo |
| Dataset | Amazon Fashion Products (Kaggle) |

---

