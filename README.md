# 📊 Binance Wallet Analyzer

Analyseur de portefeuille Binance avec graphiques de performance et rapport fiscal détaillé.

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## ✨ Fonctionnalités

- 📈 **Graphiques de Performance** : Visualisation année par année de votre portefeuille
- 💰 **Rapport Fiscal Détaillé** : Calcul des dépôts, retraits et cessions imposables
- 🚀 **Multithreading** : Récupération rapide des prix historiques (API Binance)
- 💾 **Cache Intelligent** : Les prix sont mis en cache pour accélérer les analyses futures
- 🔍 **Logs Détaillés** : Suivi complet de chaque opération
- 🌐 **Interface Web** : Drag & drop votre CSV et analysez en temps réel !

## 📋 Prérequis

- Python 3.8 ou supérieur
- pip (gestionnaire de paquets Python)
- Connexion internet (pour récupérer les prix historiques)

## 🚀 Installation Rapide

### 1. Cloner ou télécharger le projet

```bash
cd binance-wallet-analyzer
```

### 2. Créer un environnement virtuel

**macOS/Linux :**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows :**

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

## 📊 Utilisation

### Mode CLI (Ligne de Commande)

```bash
./venv/bin/python analyze_wallet_v2.py binance-transac.csv
```

**Sorties générées :**

- `report_2023.png`, `report_2024.png`, `report_2025.png` : Graphiques année par année
- `wallet_analysis.log` : Logs détaillés de l'analyse
- `price_cache.json` : Cache des prix (gardez-le pour les futures analyses !)
- Rapport fiscal dans le terminal

### Mode Web (Interface Interactive) 🌐

```bash
python app.py
```

Ouvrez votre navigateur sur `http://localhost:5000` et :

1. **Drag & Drop** votre fichier `binance-transac.csv`
2. **Suivez en temps réel** les 4 étapes d'analyse
3. **Consultez** votre dashboard interactif !

## 📁 Format du CSV

Le script attend un export Binance standard avec les colonnes suivantes :

```csv
User_ID,UTC_Time,Account,Operation,Coin,Change,Remark
809831332,2023-11-21 18:31:39,Spot,Buy Crypto With Fiat,BTC,0.00077895,Ref - ...
```

**Comment obtenir votre CSV depuis Binance :**

1. Connectez-vous à Binance
2. Allez dans **Portefeuille** > **Historique des transactions**
3. Cliquez sur **Exporter** et sélectionnez la période souhaitée
4. Téléchargez le fichier CSV

## 🏗️ Architecture du Projet

```
binance-wallet-analyzer/
├── analyze_wallet_v2.py    # Script d'analyse principal
├── app.py                   # Application web Flask
├── requirements.txt         # Dépendances Python
├── price_cache.json         # Cache des prix (généré automatiquement)
├── wallet_analysis.log      # Logs détaillés (généré automatiquement)
├── templates/
│   └── index.html          # Interface web
├── static/
│   ├── css/
│   │   └── style.css       # Styles de l'interface
│   └── js/
│       └── app.js          # Logique frontend
└── venv/                   # Environnement virtuel Python
```

## 🧪 Opérations Supportées

### Opérations Analysées

- ✅ Buy Crypto With Fiat (Achat CB externe)
- ✅ Sell Crypto For Fiat (Vente taxable)
- ✅ Deposit / Withdraw (Mouvements Fiat)
- ✅ Fiat Withdraw (Retrait bancaire)
- ✅ Binance Convert (Swap crypto-crypto)
- ✅ Transaction Buy/Sold (Trades sur le marché)
- ✅ Staking Rewards, Cashback, Airdrops
- ✅ Crypto Box, Distribution

### Opérations Ignorées

- ⏭️ Simple Earn Subscription/Redemption (Mouvements internes)
- ⏭️ Flexible Loan - Collateral Transfer
- ⏭️ Transfer Between Wallets (Interne Binance)

## 📈 Méthodologie de Calcul

### Net Investi

```
Net Investi = (Dépôts Fiat + Achats par CB) - (Retraits Fiat + Ventes vers Fiat)
```

**Explication :**

- **Entrées** : Dépôts EUR, achats directs par carte bancaire
- **Sorties** : Retraits EUR, ventes de crypto contre EUR
- Les swaps crypto-crypto ne modifient **pas** le net investi (mouvement interne)

### Plus-Value Latente

```
Plus-Value = Valeur Totale Portefeuille - Net Investi
```

### Cessions Imposables

Toutes les opérations **"Sell Crypto For Fiat"** sont considérées comme imposables.

## 🔧 Configuration Avancée

### Modifier le nombre de workers (vitesse)

Dans `analyze_wallet_v2.py` :

```python
MAX_WORKERS = 10  # Augmentez pour plus de vitesse (attention au rate limit !)
```

### Changer les devises Fiat acceptées

```python
FIAT_CURRENCIES = {'EUR', 'USD', 'GBP'}  # Ajoutez vos devises
```

## 🐛 Dépannage

### Erreur "ModuleNotFoundError"

```bash
# Assurez-vous d'utiliser le bon Python
./venv/bin/python analyze_wallet_v2.py binance-transac.csv
```

### Erreur "API Rate Limit (429)"

Le script gère automatiquement les rate limits avec un backoff exponentiel. Si cela persiste, réduisez `MAX_WORKERS`.

### Erreur "No module named 'flask'"

```bash
pip install flask flask-socketio
```

### Cache corrompu

```bash
rm price_cache.json  # Supprimez et relancez (les prix seront refetchés)
```

## 📊 Exemple de Rapport Fiscal

```
================================================================================
ANNEE 2024
================================================================================
  - Dépôts Fiat: 1500.00 €
  - Retraits Fiat: 824.65 €
  - Volume Cessions Imposables (Sell Fiat): 0.00 €

  ✓ Aucune vente vers Fiat (Sell Crypto For Fiat) détectée pour 2024
    → Le volume de cessions imposables est bien de 0.00 €
```

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à :

- Signaler des bugs
- Proposer des améliorations
- Ajouter de nouvelles fonctionnalités

## 📝 Licence

MIT License - Utilisez librement pour vos analyses personnelles.

## ⚠️ Disclaimer

**Cet outil est fourni à titre informatif uniquement.**
Les calculs fiscaux sont des **estimations** basées sur les données Binance. Pour une déclaration fiscale officielle, consultez un expert-comptable ou fiscaliste spécialisé en crypto-monnaies.

---

**Fait avec ❤️ pour la communauté crypto**
# Binance-french-taxes
# Binance-french-taxes
