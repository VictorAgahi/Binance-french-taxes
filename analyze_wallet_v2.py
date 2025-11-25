import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Force non-interactive backend (MUST be before pyplot import)
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import logging
import json
import time
import requests
from datetime import datetime, timedelta
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from collections import defaultdict
from functools import wraps

# --- Configuration ---
getcontext().prec = 28
LOG_FILE = "wallet_analysis.log"
CACHE_FILE = "price_cache.json"
BINANCE_API_URL = "https://api.binance.com/api/v3"
MAX_WORKERS = 10

# --- Mappings & Constants (From Prompt) ---
OPERATION_MAPPING = {
    'Buy Crypto With Fiat': 'buy_fiat',
    'Sell Crypto For Fiat': 'sell_fiat',
    'Transaction Buy': 'buy',
    'Transaction Sold': 'sell',
    'Transaction Revenue': 'revenue',
    'Transaction Spend': 'spend',
    'Transaction Fee': 'fee',
    'Cashback Voucher': 'cashback',
    'Deposit': 'deposit',
    'Withdraw': 'withdraw',
    'Distribution': 'distribution',
    'Staking Rewards': 'staking',
    'Binance Convert': 'convert',
    'Crypto Box': 'airdrop',
    'Simple Earn Flexible Interest': 'staking',
    'Fiat Withdraw': 'withdraw_fiat',
}

IGNORED_OPERATIONS = [
    'Simple Earn Flexible Subscription', 'Simple Earn Flexible Redemption',
    'Simple Earn Locked Subscription', 'Simple Earn Locked Redemption',
    'Flexible Loan - Collateral Transfer',
]

# --- CONFORMITÉ FISCALE FRANÇAISE (PFU - Flat Tax 30%) ---
# Article 150 VH bis du CGI : Seule la cession crypto → MONNAIE AYANT COURS LÉGAL
# constitue un événement imposable (exit du régime de sursis d'imposition)
#
# IMPORTANT : Les stablecoins (USDT, USDC, etc.) SONT des cryptoactifs.
# Une conversion crypto → stablecoin bénéficie du SURSIS d'imposition.
#
# ÉVÉNEMENTS IMPOSABLES (PFU 30%) :
#   ✅ BTC → EUR (Vente vers Euro)
#   ✅ ETH → USD (Vente vers Dollar US)
#   ✅ BTC → GBP (Vente vers Livre Sterling)
#
# ÉVÉNEMENTS NON IMPOSABLES (Sursis) :
#   ❌ BTC → USDT (Crypto vers Stablecoin)
#   ❌ ETH → BTC (Crypto vers Crypto)
#   ❌ BTC → BUSD (Crypto vers Stablecoin)

# Monnaies Fiat = Monnaies à cours légal émises par des États
# (Ces monnaies déclenchent un événement fiscal lors de la cession)
FIAT_CURRENCIES = {
    'EUR',  # Euro
    'USD',  # Dollar US
    'GBP',  # Livre Sterling
    'CHF',  # Franc Suisse
    'JPY',  # Yen Japonais
    'CAD',  # Dollar Canadien
    'AUD',  # Dollar Australien
    'NZD',  # Dollar Néo-Zélandais
    'SGD',  # Dollar de Singapour
}

# Note : Les stablecoins (USDT, USDC, BUSD, DAI, etc.) ne sont PAS dans cette liste
# car ils sont considérés comme des cryptoactifs en droit français.

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Backoff Decorator ---
def simple_backoff(max_attempts: int = 3):
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.RequestException as e:
                    if attempt == max_attempts - 1:
                        logger.warning(f"API Error after {max_attempts} attempts: {e}")
                        return None
                    time.sleep(0.5 * (2 ** attempt))
            return None
        return wrapper
    return decorator

# --- Price Cache & API Client ---
class PriceCache:
    def __init__(self, cache_file: str):
        self.cache_file = Path(cache_file)
        self.cache = self._load_cache()
        self.lock = Lock()
        self.unsaved_changes = 0

    def _load_cache(self) -> Dict[str, Any]:
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        with open(self.cache_file, 'w') as f:
            json.dump(self.cache, f)
        self.unsaved_changes = 0

    def get_price(self, symbol: str, date_str: str) -> Optional[float]:
        with self.lock:
            return self.cache.get(f"{symbol}_{date_str}")

    def set_price(self, symbol: str, date_str: str, price: float):
        with self.lock:
            self.cache[f"{symbol}_{date_str}"] = price
            self.unsaved_changes += 1
            if self.unsaved_changes > 50:
                self._save_cache()

    def save(self):
        with self.lock:
            self._save_cache()

class BinancePriceClient:
    def __init__(self, cache: PriceCache):
        self.cache = cache

    def get_price_in_eur(self, coin: str, timestamp: pd.Timestamp) -> float:
        if coin == 'EUR': return 1.0

        ts_ms = int(timestamp.timestamp() * 1000)
        ts_minute = (ts_ms // 60000) * 60000
        date_key = str(ts_minute)

        cached = self.cache.get_price(coin, date_key)
        if cached is not None: return cached

        price = self._fetch_price_api(coin, ts_minute)

        if price is not None:
            self.cache.set_price(coin, date_key, price)
            return price

        return 0.0

    @simple_backoff()
    def _fetch_price_api(self, coin: str, ts_ms: int) -> Optional[float]:
        pairs_to_try = [f"{coin}EUR", f"{coin}USDT"]

        for pair in pairs_to_try:
            url = f"{BINANCE_API_URL}/klines?symbol={pair}&interval=1m&startTime={ts_ms-60000}&endTime={ts_ms+60000}&limit=1"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    price = float(data[0][4])
                    if pair.endswith("EUR"):
                        return price
                    elif pair.endswith("USDT"):
                        usdt_eur = self._get_usdt_eur_rate(ts_ms)
                        return price * usdt_eur
            elif resp.status_code == 429:
                raise requests.exceptions.RequestException("Rate Limit")
        return None

    def _get_usdt_eur_rate(self, ts_ms: int) -> float:
        url = f"{BINANCE_API_URL}/klines?symbol=EURUSDT&interval=1m&startTime={ts_ms-60000}&endTime={ts_ms+60000}&limit=1"
        try:
            resp = requests.get(url, timeout=5)
            data = resp.json()
            if data:
                return 1.0 / float(data[0][4])
        except:
            pass
        return 0.92

    def get_batch_prices(self, coins: List[str], timestamp: pd.Timestamp) -> Dict[str, float]:
        results = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_coin = {executor.submit(self.get_price_in_eur, coin, timestamp): coin for coin in coins}
            for future in as_completed(future_to_coin):
                coin = future_to_coin[future]
                try:
                    results[coin] = future.result()
                except:
                    results[coin] = 0.0
        return results

# --- Core Logic ---

class WalletAnalyzer:
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self.price_cache = PriceCache(CACHE_FILE)
        self.price_client = BinancePriceClient(self.price_cache)
        self.df = pd.DataFrame()
        self.holdings: Dict[str, Decimal] = defaultdict(Decimal)
        self.net_invested_eur = Decimal(0)
        self.daily_snapshots = []

    def step_a_load_and_clean(self):
        logger.info("="*80)
        logger.info("Étape A: Chargement et Nettoyage...")
        logger.info("="*80)
        df = pd.read_csv(self.csv_path)
        logger.info(f"CSV chargé: {len(df)} lignes brutes")

        df.columns = [c.strip().replace('"', '') for c in df.columns]
        logger.info(f"Colonnes détectées: {list(df.columns)}")

        df['UTC_Time'] = pd.to_datetime(df['UTC_Time'])
        logger.info(f"Période couverte: {df['UTC_Time'].min()} à {df['UTC_Time'].max()}")

        df['Mapped_Op'] = df['Operation'].map(OPERATION_MAPPING).fillna('unknown')

        df_before = len(df)
        df = df[~df['Operation'].isin(IGNORED_OPERATIONS)].copy()
        df_after = len(df)
        logger.info(f"Filtrage des opérations ignorées: {df_before - df_after} transactions supprimées")

        df = df.sort_values('UTC_Time').reset_index(drop=True)
        df['Change'] = df['Change'].astype(str).apply(Decimal)

        # Count operation types
        op_counts = df['Operation'].value_counts()
        logger.info(f"Types d'opérations trouvées:")
        for op_type, count in op_counts.head(10).items():
            logger.info(f"  - {op_type}: {count}")
        if len(op_counts) > 10:
            logger.info(f"  ... et {len(op_counts) - 10} autres types")

        self.df = df
        logger.info(f"✓ {len(df)} transactions prêtes après filtrage et tri.")
        logger.info("")

    def step_b_process_flows(self):
        logger.info("="*80)
        logger.info("Étape B: Reconstruction des Flux...")
        logger.info("="*80)

        grouped = self.df.groupby('UTC_Time')
        dates = sorted(list(grouped.groups.keys()))
        total_groups = len(dates)

        logger.info(f"Nombre de groupes de transactions à traiter: {total_groups}")

        for idx, date in enumerate(dates, 1):
            group = grouped.get_group(date)
            self._process_group(date, group)
            self.daily_snapshots.append({
                'date': date,
                'holdings': self.holdings.copy(),
                'net_invested': self.net_invested_eur
            })

            # Progress logging every 100 groups
            if idx % 100 == 0 or idx == total_groups:
                logger.info(f"Progression: {idx}/{total_groups} groupes traités ({100*idx/total_groups:.1f}%)")

        self.price_cache.save()
        logger.info(f"✓ Tous les flux traités. Net Investi final: {self.net_invested_eur:.2f} EUR")
        logger.info("")

    def _process_group(self, date: pd.Timestamp, group: pd.DataFrame):
        has_fiat_deduction = any(row['Coin'] in FIAT_CURRENCIES and row['Change'] < 0 for _, row in group.iterrows())

        # Log group summary
        ops_in_group = [row['Operation'] for _, row in group.iterrows()]
        logger.debug(f"Processing group at {date} with {len(group)} operations: {set(ops_in_group)}")

        for _, row in group.iterrows():
            coin = row['Coin']
            change = row['Change']
            op = row['Mapped_Op']

            logger.debug(f"  Processing transaction: Date={date}, Coin={coin}, Change={change}, Operation={op}")

            self.holdings[coin] += change
            if self.holdings[coin] == 0:
                del self.holdings[coin]
                logger.debug(f"  {coin} holdings reached zero and removed.")
            else:
                logger.debug(f"  Current {coin} holdings: {self.holdings[coin]}")

            # --- GESTION ÉVÉNEMENTS FISCAUX : Uniquement FIAT (Monnaies à cours légal) ---
            # Les conversions crypto → stablecoin (ex: BTC → USDT) ne sont PAS imposables
            if coin in FIAT_CURRENCIES:
                if op == 'deposit':
                    self.net_invested_eur += change
                    logger.debug(f"  Fiat deposit: {change}. Net invested: {self.net_invested_eur}")
                elif op == 'withdraw_fiat':
                    self.net_invested_eur += change # Change is negative for withdrawals
                    logger.debug(f"  Fiat withdrawal: {change}. Net invested: {self.net_invested_eur}")
                elif op == 'sell_fiat':
                    # ÉVÉNEMENT TAXABLE : Vente crypto → Fiat (EUR, USD, GBP, etc.)
                    self.net_invested_eur -= change # Subtract sales to fiat from net invested (Cash Out)
                    logger.info(f"  💶 ÉVÉNEMENT TAXABLE - Sell to Fiat ({coin}): +{change} {coin}. Net invested reduced to: {self.net_invested_eur:.2f} EUR")

            # Handle Card Buys (Buy Crypto With Fiat without internal Fiat deduction)
            if op == 'buy_fiat' and not has_fiat_deduction:
                if coin not in FIAT_CURRENCIES:
                    price = self.price_client.get_price_in_eur(coin, date)
                    val_eur = Decimal(change) * Decimal(price)
                    self.net_invested_eur += val_eur
                    logger.info(f"  External Card Buy detected: {change} {coin} @ {price:.4f} EUR = {val_eur:.2f} EUR. Net invested: {self.net_invested_eur:.2f}")

    def step_c_visualize(self):
        logger.info("="*80)
        logger.info("Étape C: Génération des Graphiques...")
        logger.info("="*80)

        data = [{'date': s['date'], 'net_invested': float(s['net_invested']), 'holdings': s['holdings']} for s in self.daily_snapshots]
        df_res = pd.DataFrame(data).set_index('date')
        df_daily = df_res.resample('D').last().ffill()

        dates = df_daily.index
        total_values = []

        logger.info(f"Valorisation de {len(dates)} jours (du {dates[0].strftime('%Y-%m-%d')} au {dates[-1].strftime('%Y-%m-%d')})...")

        for date in dates:
            holdings = df_daily.loc[date, 'holdings']
            if not isinstance(holdings, dict): holdings = {}
            active_coins = [c for c, q in holdings.items() if q > Decimal("0.000001")]

            if not active_coins:
                total_values.append(0.0)
                continue

            prices = self.price_client.get_batch_prices(active_coins, date)
            val = sum(float(holdings[c]) * prices.get(c, 0.0) for c in active_coins)
            total_values.append(val)

        df_daily['total_value'] = total_values

        years = sorted(list(set(d.year for d in dates)))
        for year in years:
            df_year = df_daily[df_daily.index.year == year]
            if df_year.empty: continue

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), gridspec_kw={'height_ratios': [3, 1]})

            ax1.plot(df_year.index, df_year['total_value'], label='Valeur Portefeuille (€)', color='#f3ba2f', linewidth=2)
            ax1.plot(df_year.index, df_year['net_invested'], label='Net Investi (€)', color='#1e2329', linestyle='--', linewidth=1.5)
            ax1.set_title(f'Performance Portefeuille {year}')
            ax1.set_ylabel('Montant (€)')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b'))

            ax2.text(0.5, 0.5, "Données PnL Réalisé non disponibles (Calcul FIFO complexe requis)",
                     ha='center', va='center', transform=ax2.transAxes)
            ax2.set_title('PnL Réalisé (Événements Taxables)')

            plt.tight_layout()
            plt.savefig(f'report_{year}.png')
            logger.info(f"Graphique généré : report_{year}.png")

    def step_d_report(self):
        logger.info("="*80)
        logger.info("Étape D: Rapport Fiscal...")
        logger.info("="*80)
        df = self.df
        years = df['UTC_Time'].dt.year.unique()

        print("\n" + "="*80)
        print("=== RAPPORT FISCAL DETAILLE ===")
        print("="*80)

        for year in sorted(years):
            df_year = df[df['UTC_Time'].dt.year == year]
            deposits = Decimal(0)
            withdrawals = Decimal(0)
            taxable_volume_fiat = Decimal(0)  # Ventes vers Fiat (EUR, USD, GBP, etc.)

            # Track all sell_fiat transactions
            sell_fiat_transactions = []
            deposit_transactions = []
            withdrawal_transactions = []

            for _, row in df_year.iterrows():
                op = row['Mapped_Op']
                change = row['Change']
                coin = row['Coin']
                date = row['UTC_Time']
                operation = row['Operation']

                # --- Événements FIAT uniquement (Monnaies à cours légal) ---
                if coin in FIAT_CURRENCIES:
                    if op == 'deposit' and change > 0:
                        deposits += change
                        deposit_transactions.append({
                            'date': date,
                            'operation': operation,
                            'coin': coin,
                            'amount': change
                        })
                    elif op in ['withdraw', 'withdraw_fiat'] and change < 0:
                        withdrawals += abs(change)
                        withdrawal_transactions.append({
                            'date': date,
                            'operation': operation,
                            'coin': coin,
                            'amount': abs(change)
                        })
                    # --- ÉVÉNEMENTS TAXABLES vers FIAT (EUR, USD, GBP, etc.) ---
                    elif op == 'sell_fiat' and change > 0:
                        taxable_volume_fiat += change
                        sell_fiat_transactions.append({
                            'date': date,
                            'operation': operation,
                            'coin': coin,
                            'amount': change
                        })

            print(f"\n{'='*80}")
            print(f"ANNEE {year}")
            print(f"{'='*80}")
            print(f"  - Dépôts Fiat: {deposits:.2f} €")
            print(f"  - Retraits Fiat: {withdrawals:.2f} €")
            print(f"  - Volume Cessions Imposables (Sell Fiat): {taxable_volume_fiat:.2f} €")

            # Show all deposit transactions
            if deposit_transactions:
                print(f"\n  Détail des Dépôts ({len(deposit_transactions)} transactions):")
                for i, tx in enumerate(deposit_transactions[:10], 1):  # Show first 10
                    print(f"    {i}. {tx['date'].strftime('%Y-%m-%d %H:%M')} | {tx['operation']} | {tx['coin']} | {tx['amount']:.2f}")
                if len(deposit_transactions) > 10:
                    print(f"    ... et {len(deposit_transactions) - 10} autres dépôts")

            # Show all withdrawal transactions
            if withdrawal_transactions:
                print(f"\n  Détail des Retraits ({len(withdrawal_transactions)} transactions):")
                for i, tx in enumerate(withdrawal_transactions[:10], 1):  # Show first 10
                    print(f"    {i}. {tx['date'].strftime('%Y-%m-%d %H:%M')} | {tx['operation']} | {tx['coin']} | {tx['amount']:.2f}")
                if len(withdrawal_transactions) > 10:
                    print(f"    ... et {len(withdrawal_transactions) - 10} autres retraits")

            # IMPORTANT: Show all sell_fiat transactions to prove the calculation
            if sell_fiat_transactions:
                print(f"\n  💶 Ventes vers FIAT - IMPOSABLES ({len(sell_fiat_transactions)} transactions):")
                print(f"     (EUR, USD, GBP, CHF, etc. - Monnaies à cours légal)")
                total_check = Decimal(0)
                for i, tx in enumerate(sell_fiat_transactions, 1):
                    print(f"    {i}. {tx['date'].strftime('%Y-%m-%d %H:%M')} | {tx['operation']} | {tx['coin']} | +{tx['amount']:.2f}")
                    total_check += tx['amount']
                print(f"\n    TOTAL VÉRIFICATIF: {total_check:.2f} (doit correspondre à {taxable_volume_fiat:.2f})")
                if abs(total_check - taxable_volume_fiat) < Decimal("0.01"):
                    print(f"    ✓ COHÉRENCE CONFIRMÉE")
                else:
                    print(f"    ✗ ATTENTION: INCOHÉRENCE DÉTECTÉE!")
            else:
                print(f"\n  ✓ Aucune vente vers Fiat détectée pour {year}")
                print(f"    → Le volume de cessions imposables est bien de 0.00")

            print(f"\n  ℹ️  Note : Les conversions crypto → stablecoin (BTC → USDT) bénéficient du sursis d'imposition")

        print("\n" + "="*80)
        logger.info("Rapport fiscal généré avec succès")

    def run(self):
        self.step_a_load_and_clean()
        self.step_b_process_flows()
        self.step_c_visualize()
        self.step_d_report()

if __name__ == "__main__":
    import sys
    csv_file = sys.argv[1] if len(sys.argv) > 1 else "binance-transac.csv"
    if not Path(csv_file).exists():
        print(f"Erreur: Fichier {csv_file} introuvable.")
        sys.exit(1)
    analyzer = WalletAnalyzer(csv_file)
    analyzer.run()
