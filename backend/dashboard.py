"""
DUTCHKEM TRADER - WEB DASHBOARD
================================
Start/Stop trading, MT5 detection, account details.
"""

import json
import os
import sys
import webbrowser
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django
django.setup()

from flask import Flask, jsonify, render_template_string, send_from_directory
import MetaTrader5 as mt5

app = Flask(__name__)

# Paths
TRADING_DIR = Path("trades_complete")
STATE_FILE = TRADING_DIR / "complete_state.json"
LOG_FILE = TRADING_DIR / "complete_trades.jsonl"
CONTROL_FILE = TRADING_DIR / "trading_control.json"
MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
MT5_LOGIN = 476963617
MT5_PASSWORD = "Christ@5436"
MT5_SERVER = "Exness-MT5Trial9"

# Import trading functions
sys.path.insert(0, os.path.dirname(__file__))
from live_trading_complete import (
    start_trading, stop_trading, get_trading_status,
    detect_mt5, get_account_details, connect_mt5,
    WATCHLIST, TIMEFRAMES, CONFIG
)


# ═══════════════════════════════════════════════════════════════
# HTML TEMPLATE
# ═══════════════════════════════════════════════════════════════
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dutchkem Trader - Live Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0a0a0f; color: #e0e0e0; }
        .header { background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 20px 40px; border-bottom: 2px solid #0f3460; }
        .header h1 { color: #00d4ff; font-size: 28px; }
        .header .subtitle { color: #888; font-size: 14px; margin-top: 5px; }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; margin-top: 20px; }
        .card { background: #12121a; border: 1px solid #2a2a3a; border-radius: 12px; padding: 20px; }
        .card h2 { color: #00d4ff; font-size: 18px; margin-bottom: 15px; display: flex; align-items: center; gap: 10px; }
        .card h2 .icon { font-size: 24px; }
        .status-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #1a1a2a; }
        .status-row:last-child { border-bottom: none; }
        .status-label { color: #888; }
        .status-value { color: #fff; font-weight: 600; }
        .status-value.positive { color: #00ff88; }
        .status-value.negative { color: #ff4444; }
        .status-value.warning { color: #ffaa00; }
        .status-value.info { color: #00d4ff; }
        .btn-group { display: flex; gap: 10px; margin-top: 15px; }
        .btn { padding: 12px 30px; border: none; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; transition: all 0.3s; flex: 1; }
        .btn-start { background: linear-gradient(135deg, #00ff88, #00cc6a); color: #000; }
        .btn-start:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(0, 255, 136, 0.3); }
        .btn-start:disabled { background: #333; color: #666; cursor: not-allowed; transform: none; box-shadow: none; }
        .btn-stop { background: linear-gradient(135deg, #ff4444, #cc0000); color: #fff; }
        .btn-stop:hover { transform: translateY(-2px); box-shadow: 0 5px 20px rgba(255, 68, 68, 0.3); }
        .btn-stop:disabled { background: #333; color: #666; cursor: not-allowed; transform: none; box-shadow: none; }
        .btn-refresh { background: linear-gradient(135deg, #00d4ff, #0088cc); color: #000; }
        .btn-refresh:hover { transform: translateY(-2px); }
        .improvement-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
        .improvement-item { padding: 10px; background: #1a1a2a; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; }
        .improvement-item .name { font-size: 13px; }
        .improvement-item .badge { padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
        .badge.active { background: #00ff88; color: #000; }
        .badge.inactive { background: #333; color: #888; }
        .badge.week3 { background: #ffaa00; color: #000; }
        .positions-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        .positions-table th { text-align: left; padding: 10px; background: #1a1a2a; color: #00d4ff; font-size: 12px; text-transform: uppercase; }
        .positions-table td { padding: 10px; border-bottom: 1px solid #1a1a2a; font-size: 13px; }
        .positions-table tr:hover { background: #1a1a2a; }
        .badge-buy { background: #00ff88; color: #000; padding: 2px 6px; border-radius: 4px; font-size: 11px; }
        .badge-sell { background: #ff4444; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 11px; }
        .mt5-status { display: flex; gap: 15px; margin-top: 10px; }
        .mt5-indicator { display: flex; align-items: center; gap: 8px; padding: 8px 15px; background: #1a1a2a; border-radius: 8px; }
        .mt5-dot { width: 10px; height: 10px; border-radius: 50%; }
        .mt5-dot.green { background: #00ff88; box-shadow: 0 0 10px #00ff88; }
        .mt5-dot.red { background: #ff4444; box-shadow: 0 0 10px #ff4444; }
        .mt5-dot.yellow { background: #ffaa00; box-shadow: 0 0 10px #ffaa00; }
        .account-type { display: inline-block; padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; }
        .account-type.demo { background: #ffaa00; color: #000; }
        .account-type.live { background: #00ff88; color: #000; }
        .loading { text-align: center; padding: 40px; color: #888; }
        .pulse { animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .full-width { grid-column: 1 / -1; }
        .deals-list { max-height: 300px; overflow-y: auto; }
        .deal-item { padding: 8px; background: #1a1a2a; border-radius: 6px; margin-bottom: 5px; font-size: 12px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>DUTCHKEM TRADER</h1>
        <div class="subtitle">Live Trading Dashboard | 27 Instruments x 7 Timeframes</div>
    </div>

    <div class="container">
        <!-- MT5 Status -->
        <div class="card">
            <h2><span class="icon">MT5</span> Connection Status</h2>
            <div id="mt5-status" class="mt5-status">
                <div class="loading">Loading...</div>
            </div>
        </div>

        <div class="grid">
            <!-- Trading Controls -->
            <div class="card">
                <h2><span class="icon">Trading</span> Controls</h2>
                <div class="btn-group">
                    <button class="btn btn-start" id="btn-start" onclick="startTrading()">START TRADING</button>
                    <button class="btn btn-stop" id="btn-stop" onclick="stopTrading()">STOP TRADING</button>
                </div>
                <div class="btn-group">
                    <button class="btn btn-refresh" onclick="refreshData()">REFRESH</button>
                </div>
                <div id="trading-status" style="margin-top: 15px;"></div>
            </div>

            <!-- Account Details -->
            <div class="card">
                <h2><span class="icon">Account</span> Details</h2>
                <div id="account-details">
                    <div class="loading">Connect MT5 to view account</div>
                </div>
            </div>

            <!-- Active Improvements -->
            <div class="card">
                <h2><span class="icon">Improvements</span> Status</h2>
                <div id="improvements" class="improvement-grid">
                    <div class="loading">Loading...</div>
                </div>
            </div>

            <!-- Performance -->
            <div class="card">
                <h2><span class="icon">Performance</span> Stats</h2>
                <div id="performance">
                    <div class="loading">No data yet</div>
                </div>
            </div>

            <!-- Open Positions -->
            <div class="card full-width">
                <h2><span class="icon">Open</span> Positions</h2>
                <div id="positions">
                    <div class="loading">No open positions</div>
                </div>
            </div>

            <!-- Recent Trades -->
            <div class="card full-width">
                <h2><span class="icon">Recent</span> Trades</h2>
                <div id="trades" class="deals-list">
                    <div class="loading">No trades yet</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let tradingActive = false;

        async function refreshData() {
            try {
                // Get trading status
                const response = await fetch('/api/status');
                const data = await response.json();

                tradingActive = data.active;
                updateButtons();
                updateMT5Status(data.mt5);
                updateAccountDetails(data.account);
                updatePerformance(data.state);
                updateImprovements(data.state);

                // Get positions
                const posResponse = await fetch('/api/positions');
                const positions = await posResponse.json();
                updatePositions(positions);

                // Get trades
                const tradesResponse = await fetch('/api/trades');
                const trades = await tradesResponse.json();
                updateTrades(trades);

            } catch (error) {
                console.error('Error refreshing data:', error);
            }
        }

        function updateButtons() {
            document.getElementById('btn-start').disabled = tradingActive;
            document.getElementById('btn-stop').disabled = !tradingActive;

            const statusDiv = document.getElementById('trading-status');
            if (tradingActive) {
                statusDiv.innerHTML = '<span class="badge active pulse">TRADING ACTIVE</span>';
            } else {
                statusDiv.innerHTML = '<span class="badge inactive">STOPPED</span>';
            }
        }

        function updateMT5Status(mt5) {
            const div = document.getElementById('mt5-status');
            if (!mt5) {
                div.innerHTML = '<div class="mt5-indicator"><div class="mt5-dot red"></div>Cannot detect MT5</div>';
                return;
            }

            div.innerHTML = `
                <div class="mt5-indicator">
                    <div class="mt5-dot ${mt5.installed ? 'green' : 'red'}"></div>
                    MT5 ${mt5.installed ? 'Installed' : 'Not Found'}
                </div>
                <div class="mt5-indicator">
                    <div class="mt5-dot ${mt5.running ? 'green' : 'red'}"></div>
                    Terminal ${mt5.running ? 'Running' : 'Not Running'}
                </div>
                <div class="mt5-indicator">
                    <div class="mt5-dot ${mt5.connected ? 'green' : 'red'}"></div>
                    Broker ${mt5.connected ? 'Connected' : 'Disconnected'}
                </div>
            `;
        }

        function updateAccountDetails(account) {
            const div = document.getElementById('account-details');
            if (!account) {
                div.innerHTML = '<div class="loading">Connect MT5 to view account</div>';
                return;
            }

            div.innerHTML = `
                <div class="status-row">
                    <span class="status-label">Login</span>
                    <span class="status-value info">${account.login}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Server</span>
                    <span class="status-value">${account.server}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Type</span>
                    <span class="account-type ${account.account_type.toLowerCase()}">${account.account_type}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Balance</span>
                    <span class="status-value positive">$${account.balance.toLocaleString()}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Equity</span>
                    <span class="status-value">$${account.equity.toLocaleString()}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Free Margin</span>
                    <span class="status-value">$${account.margin_free.toLocaleString()}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Leverage</span>
                    <span class="status-value info">1:${account.leverage}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Profit</span>
                    <span class="status-value ${account.profit >= 0 ? 'positive' : 'negative'}">$${account.profit >= 0 ? '+' : ''}${account.profit.toLocaleString()}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Open Positions</span>
                    <span class="status-value">${account.positions_count}</span>
                </div>
            `;
        }

        function updatePerformance(state) {
            const div = document.getElementById('performance');
            if (!state || !state.total_trades) {
                div.innerHTML = '<div class="loading">No trades yet</div>';
                return;
            }

            const wr = state.total_trades > 0 ? ((state.wins / state.total_trades) * 100).toFixed(1) : 0;

            div.innerHTML = `
                <div class="status-row">
                    <span class="status-label">Total Trades</span>
                    <span class="status-value info">${state.total_trades}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Wins</span>
                    <span class="status-value positive">${state.wins}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Losses</span>
                    <span class="status-value negative">${state.losses}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Win Rate</span>
                    <span class="status-value ${wr >= 50 ? 'positive' : 'negative'}">${wr}%</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Total P&L</span>
                    <span class="status-value ${state.total_pnl >= 0 ? 'positive' : 'negative'}">$${state.total_pnl >= 0 ? '+' : ''}${state.total_pnl.toFixed(2)}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Week</span>
                    <span class="status-value info">${state.week_number || 1}</span>
                </div>
                <div class="status-row">
                    <span class="status-label">Consecutive Losses</span>
                    <span class="status-value ${state.consecutive_losses >= 3 ? 'warning' : ''}">${state.consecutive_losses}</span>
                </div>
            `;
        }

        function updateImprovements(state) {
            const div = document.getElementById('improvements');
            const improvements = state?.active_improvements || {};

            const items = [
                { name: 'Correlation Filter', key: 'correlation_filter', week: 1 },
                { name: 'Dynamic Risk', key: 'dynamic_risk', week: 1 },
                { name: 'Spread Filter', key: 'spread_filter', week: 1 },
                { name: 'News Avoidance', key: 'news_avoidance', week: 3 },
                { name: 'Breakout Detection', key: 'breakout_detection', week: 3 },
                { name: 'Mean Reversion', key: 'mean_reversion', week: 3 },
                { name: 'Position Scaling', key: 'position_scaling', week: 3 },
            ];

            div.innerHTML = items.map(item => {
                const active = improvements[item.key];
                const badge = active ? 'active' : (item.week > 1 ? 'week3' : 'inactive');
                const label = active ? 'ACTIVE' : (item.week > 1 ? 'WEEK 3' : 'INACTIVE');
                return `
                    <div class="improvement-item">
                        <span class="name">${item.name}</span>
                        <span class="badge ${badge}">${label}</span>
                    </div>
                `;
            }).join('');
        }

        function updatePositions(positions) {
            const div = document.getElementById('positions');
            if (!positions || positions.length === 0) {
                div.innerHTML = '<div class="loading">No open positions</div>';
                return;
            }

            div.innerHTML = `
                <table class="positions-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Type</th>
                            <th>Volume</th>
                            <th>Entry</th>
                            <th>Current</th>
                            <th>SL</th>
                            <th>TP</th>
                            <th>Profit</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${positions.map(p => `
                            <tr>
                                <td>${p.symbol}</td>
                                <td><span class="badge-${p.type.toLowerCase()}">${p.type}</span></td>
                                <td>${p.volume}</td>
                                <td>${p.price_open.toFixed(5)}</td>
                                <td>${p.price_current.toFixed(5)}</td>
                                <td>${p.sl.toFixed(5)}</td>
                                <td>${p.tp.toFixed(5)}</td>
                                <td class="${p.profit >= 0 ? 'positive' : 'negative'}">$${p.profit >= 0 ? '+' : ''}${p.profit.toFixed(2)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        }

        function updateTrades(trades) {
            const div = document.getElementById('trades');
            if (!trades || trades.length === 0) {
                div.innerHTML = '<div class="loading">No trades yet</div>';
                return;
            }

            div.innerHTML = trades.slice(-20).reverse().map(t => `
                <div class="deal-item">
                    <strong>${t.symbol}</strong> ${t.action} | 
                    Entry: ${t.entry_price} → Exit: ${t.exit_price} |
                    P&L: <span class="${t.pnl >= 0 ? 'positive' : 'negative'}">$${t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(2)}</span>
                    | TFs: ${t.tf_agreement}/7
                </div>
            `).join('');
        }

        async function startTrading() {
            const response = await fetch('/api/start', { method: 'POST' });
            const data = await response.json();
            alert(data.message || data.status);
            refreshData();
        }

        async function stopTrading() {
            if (!confirm('Stop trading?')) return;
            const response = await fetch('/api/stop', { method: 'POST' });
            const data = await response.json();
            alert(data.message || data.status);
            refreshData();
        }

        // Auto-refresh every 5 seconds
        setInterval(refreshData, 5000);
        refreshData();
    </script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════
@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route("/api/status")
def api_status():
    status = get_trading_status()
    # Add MT5 connection status
    mt5_info = detect_mt5()
    try:
        if mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            mt5_info["connected"] = True
            mt5.shutdown()
        else:
            mt5_info["connected"] = False
    except:
        mt5_info["connected"] = False
    status["mt5"] = mt5_info
    return jsonify(status)


@app.route("/api/start", methods=["POST"])
def api_start():
    result = start_trading()
    return jsonify({"status": "started", "message": "Trading started!"})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    result = stop_trading()
    return jsonify({"status": "stopped", "message": "Trading stopped."})


@app.route("/api/positions")
def api_positions():
    try:
        if mt5.initialize(path=MT5_PATH, login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            positions = mt5.positions_get()
            mt5.shutdown()
            if positions:
                return jsonify([{
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": "BUY" if p.type == 0 else "SELL",
                    "volume": p.volume,
                    "price_open": p.price_open,
                    "price_current": p.price_current,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": p.profit,
                } for p in positions])
        return jsonify([])
    except:
        return jsonify([])


@app.route("/api/trades")
def api_trades():
    trades = []
    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, "r") as f:
                for line in f:
                    if line.strip():
                        trades.append(json.loads(line))
        except:
            pass
    return jsonify(trades[-50:])  # Last 50 trades


@app.route("/api/account")
def api_account():
    account = get_account_details()
    return jsonify(account or {})


@app.route("/api/config")
def api_config():
    return jsonify({
        "watchlist": WATCHLIST,
        "timeframes": list(TIMEFRAMES.keys()),
        "config": {k: v for k, v in CONFIG.items() if not callable(v)},
    })


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  DUTCHKEM TRADER - DASHBOARD")
    print("  http://localhost:5000")
    print("=" * 60)
    
    # Open browser
    webbrowser.open("http://localhost:5000")
    
    app.run(host="0.0.0.0", port=5000, debug=False)
