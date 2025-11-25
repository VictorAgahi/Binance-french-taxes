from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import os
import json
import logging
from pathlib import Path
from datetime import datetime
import threading
from werkzeug.utils import secure_filename

# Import our analyzer
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_wallet_v2 import WalletAnalyzer, PriceCache, BinancePriceClient

app = Flask(__name__)
app.config['SECRET_KEY'] = 'binance-analyzer-secret-key'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Create upload folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Store analysis results
current_analysis = {
    'status': 'idle',
    'progress': 0,
    'message': '',
    'results': None,
    'error': None
}

class WebSocketLogger(logging.Handler):
    """Custom logger that sends logs via WebSocket"""
    def emit(self, record):
        log_entry = self.format(record)
        socketio.emit('log', {'message': log_entry, 'level': record.levelname})

def run_analysis(csv_path):
    """Run the analysis in a background thread"""
    global current_analysis

    try:
        current_analysis['status'] = 'running'
        current_analysis['progress'] = 0
        current_analysis['error'] = None

        # Setup custom logger
        web_logger = WebSocketLogger()
        web_logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        web_logger.setFormatter(formatter)

        # Add to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(web_logger)

        socketio.emit('status', {'status': 'running', 'step': 'Initialisation'})

        # Create analyzer
        analyzer = WalletAnalyzer(csv_path)

        # Step A
        socketio.emit('status', {'status': 'running', 'step': 'Étape A: Chargement des données', 'progress': 10})
        analyzer.step_a_load_and_clean()

        # Step B
        socketio.emit('status', {'status': 'running', 'step': 'Étape B: Reconstruction des flux', 'progress': 30})
        analyzer.step_b_process_flows()

        # Step C
        socketio.emit('status', {'status': 'running', 'step': 'Étape C: Génération des graphiques', 'progress': 60})
        analyzer.step_c_visualize()

        # Step D
        socketio.emit('status', {'status': 'running', 'step': 'Étape D: Rapport fiscal', 'progress': 85})

        # Collect fiscal report data instead of printing
        fiscal_data = collect_fiscal_data(analyzer)

        # Collect chart data
        chart_data = collect_chart_data(analyzer)

        # Collect EUR transactions
        eur_transactions = collect_eur_transactions(analyzer)

        current_analysis['results'] = {
            'fiscal_report': fiscal_data,
            'charts': chart_data,
            'eur_transactions': eur_transactions,
            'total_transactions': len(analyzer.df),
            'final_wallet': {coin: float(qty) for coin, qty in analyzer.holdings.items()},
            'net_invested': float(analyzer.net_invested_eur)
        }

        current_analysis['status'] = 'completed'
        current_analysis['progress'] = 100
        socketio.emit('status', {'status': 'completed', 'step': 'Analyse terminée !', 'progress': 100})
        socketio.emit('results', current_analysis['results'])

        # Remove custom handler
        root_logger.removeHandler(web_logger)

    except Exception as e:
        current_analysis['status'] = 'error'
        current_analysis['error'] = str(e)
        socketio.emit('error', {'message': str(e)})
        logging.error(f"Analysis error: {e}", exc_info=True)

def collect_fiscal_data(analyzer):
    """Collect fiscal report data from analyzer - CONFORMITÉ FISCALE FRANÇAISE (PFU)"""
    df = analyzer.df
    years = df['UTC_Time'].dt.year.unique()
    fiscal_data = {}

    from decimal import Decimal

    # --- CONFORMITÉ FISCALE FRANÇAISE (PFU - Flat Tax 30%) ---
    # Seules les cessions crypto → monnaies FIAT (EUR, USD, GBP, etc.) sont imposables
    # Les conversions crypto → stablecoin (BTC → USDT) bénéficient du sursis d'imposition
    FIAT_CURRENCIES = {'EUR', 'USD', 'GBP', 'CHF', 'JPY', 'CAD', 'AUD', 'NZD', 'SGD'}

    for year in sorted(years):
        df_year = df[df['UTC_Time'].dt.year == year]
        deposits = Decimal(0)
        withdrawals = Decimal(0)
        taxable_volume = Decimal(0)  # Ventes vers Fiat uniquement

        sell_fiat_transactions = []

        for _, row in df_year.iterrows():
            op = row['Mapped_Op']
            change = row['Change']
            coin = row['Coin']

            # Événements FIAT uniquement (Monnaies à cours légal)
            if coin in FIAT_CURRENCIES:
                if op == 'deposit' and change > 0:
                    deposits += change
                elif op in ['withdraw', 'withdraw_fiat'] and change < 0:
                    withdrawals += abs(change)
                elif op == 'sell_fiat' and change > 0:
                    taxable_volume += change
                    sell_fiat_transactions.append({
                        'date': row['UTC_Time'].strftime('%Y-%m-%d %H:%M'),
                        'operation': row['Operation'],
                        'coin': coin,
                        'amount': float(change)
                    })

        fiscal_data[str(year)] = {
            'deposits': float(deposits),
            'withdrawals': float(withdrawals),
            'taxable_volume': float(taxable_volume),
            'sell_transactions': sell_fiat_transactions
        }

    return fiscal_data

def collect_chart_data(analyzer):
    """Collect chart data for visualization by year"""
    import pandas as pd
    from decimal import Decimal

    # Prepare daily data
    data = [{'date': s['date'], 'net_invested': float(s['net_invested']), 'holdings': s['holdings']}
            for s in analyzer.daily_snapshots]
    df_res = pd.DataFrame(data).set_index('date')
    df_daily = df_res.resample('D').last().ffill()

    dates = df_daily.index
    years = sorted(list(set(d.year for d in dates)))

    # Organize data by year
    charts_by_year = {}

    for year in years:
        year_dates = [d for d in dates if d.year == year]
        if not year_dates:
            continue

        year_data = {
            'dates': [d.strftime('%Y-%m-%d') for d in year_dates],
            'net_invested': [float(df_daily.loc[d, 'net_invested']) for d in year_dates],
            'portfolio_values': []
        }

        # Calculate portfolio values for this year
        for date in year_dates:
            holdings = df_daily.loc[date, 'holdings']
            if isinstance(holdings, dict):
                # Get prices from cache if available
                active_coins = [c for c, q in holdings.items() if q > Decimal("0.000001")]
                if active_coins:
                    # Use price client to get values
                    prices = analyzer.price_client.get_batch_prices(active_coins, date)
                    val = sum(float(holdings[c]) * prices.get(c, 0.0) for c in active_coins)
                    year_data['portfolio_values'].append(val)
                else:
                    year_data['portfolio_values'].append(0.0)
            else:
                year_data['portfolio_values'].append(0.0)

        charts_by_year[str(year)] = year_data

    return charts_by_year


def collect_eur_transactions(analyzer):
    """Collect all EUR transactions categorized by year and type"""
    df = analyzer.df
    years = df['UTC_Time'].dt.year.unique()
    eur_data = {}

    from decimal import Decimal

    for year in sorted(years):
        df_year = df[df['UTC_Time'].dt.year == year]

        deposits = []
        withdrawals = []
        converts = []

        # Group by timestamp to handle multi-line operations
        grouped = df_year.groupby('UTC_Time')

        for timestamp, group in grouped:
            # Check if this group involves EUR
            eur_rows = group[group['Coin'] == 'EUR']

            if len(eur_rows) == 0:
                continue

            # Determine operation type
            operations = set(group['Operation'].values)

            # DEPOSITS
            if 'Deposit' in operations:
                for _, row in eur_rows.iterrows():
                    if row['Change'] > 0:
                        deposits.append({
                            'date': row['UTC_Time'].strftime('%Y-%m-%d %H:%M'),
                            'operation': 'Deposit',
                            'amount': float(row['Change']),
                            'coin': 'EUR'
                        })

            # WITHDRAWALS
            elif 'Fiat Withdraw' in operations:
                for _, row in eur_rows.iterrows():
                    if row['Change'] < 0:
                        withdrawals.append({
                            'date': row['UTC_Time'].strftime('%Y-%m-%d %H:%M'),
                            'operation': 'Fiat Withdraw',
                            'amount': float(abs(row['Change'])),
                            'coin': 'EUR'
                        })

            # CONVERTS (Binance Convert or Sell Crypto For Fiat)
            elif 'Binance Convert' in operations or 'Sell Crypto For Fiat' in operations:
                # Find the other coin involved
                other_coins = group[group['Coin'] != 'EUR']

                for _, eur_row in eur_rows.iterrows():
                    eur_change = float(eur_row['Change'])

                    # Determine direction
                    if eur_change > 0:
                        # Received EUR (sold crypto → EUR)
                        if len(other_coins) > 0:
                            from_coin = other_coins.iloc[0]['Coin']
                            converts.append({
                                'date': eur_row['UTC_Time'].strftime('%Y-%m-%d %H:%M'),
                                'operation': 'Convert',
                                'from_coin': from_coin,
                                'to_coin': 'EUR',
                                'amount': eur_change,
                                'direction': 'to_eur'
                            })
                    else:
                        # Spent EUR (EUR → bought crypto)
                        if len(other_coins) > 0:
                            to_coin = other_coins.iloc[0]['Coin']
                            converts.append({
                                'date': eur_row['UTC_Time'].strftime('%Y-%m-%d %H:%M'),
                                'operation': 'Convert',
                                'from_coin': 'EUR',
                                'to_coin': to_coin,
                                'amount': abs(eur_change),
                                'direction': 'from_eur'
                            })

        eur_data[str(year)] = {
            'deposits': deposits,
            'withdrawals': withdrawals,
            'converts': converts,
            'total_deposits': sum(d['amount'] for d in deposits),
            'total_withdrawals': sum(w['amount'] for w in withdrawals),
            'total_converts_to_eur': sum(c['amount'] for c in converts if c['direction'] == 'to_eur'),
            'total_converts_from_eur': sum(c['amount'] for c in converts if c['direction'] == 'from_eur')
        }

    return eur_data


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and file.filename.endswith('.csv'):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Start analysis in background thread
        thread = threading.Thread(target=run_analysis, args=(filepath,))
        thread.daemon = True
        thread.start()

        return jsonify({'success': True, 'message': 'Analysis started'})

    return jsonify({'error': 'Invalid file type. Only CSV files are accepted.'}), 400

@app.route('/status')
def get_status():
    return jsonify(current_analysis)

@socketio.on('connect')
def handle_connect():
    emit('connected', {'data': 'Connected to Binance Analyzer'})

if __name__ == '__main__':
    print("🚀 Starting Binance Wallet Analyzer Web App...")
    print("📊 Open your browser at: http://localhost:5000")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
