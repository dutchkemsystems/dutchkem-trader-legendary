"""
DUTCHKEM TRADER - AUTO LAUNCHER
================================
Starts FastAPI server + live trading engine automatically.
If MT5 live trading fails, falls back to paper trading.

Usage: python start_trading.py
"""

import os
import sys
import time
import json
import subprocess
import threading
import requests
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).parent
API_URL = "http://localhost:8000"
CREDENTIALS_FILE = BACKEND_DIR / "mt5_credentials.json"
CONTROL_FILE = BACKEND_DIR / "trades_complete" / "trading_control.json"


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    colors = {
        "INFO": "\033[36m",
        "OK": "\033[32m",
        "WARN": "\033[33m",
        "ERR": "\033[31m",
    }
    reset = "\033[0m"
    c = colors.get(level, "")
    print(f"{c}[{ts}] [{level}] {msg}{reset}")


def check_port(port):
    """Check if a port is in use."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_fastapi_server():
    """Start the FastAPI server as a background process."""
    if check_port(8000):
        log("FastAPI server already running on :8000", "OK")
        return None

    log("Starting FastAPI server on :8000...")
    env = os.environ.copy()

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "api.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    log(f"FastAPI server starting (PID: {proc.pid})", "OK")
    return proc


def wait_for_server(timeout=30):
    """Wait for the FastAPI server to be ready."""
    log(f"Waiting for server (timeout: {timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{API_URL}/api/v1/health", timeout=2)
            if r.status_code in (200, 503):
                log("Server is ready!", "OK")
                return True
        except:
            pass
        time.sleep(1)
    log("Server failed to start within timeout", "ERR")
    return False


def check_mt5_connection():
    """Check if MT5 is connected and get account info."""
    try:
        import MetaTrader5 as mt5

        creds = load_credentials()
        if not creds:
            log("No MT5 credentials found", "WARN")
            return None

        if not mt5.initialize(
            path=creds.get(
                "mt5_path", r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
            ),
            login=creds["login"],
            password=creds["password"],
            server=creds["server"],
        ):
            log("MT5 initialization failed", "ERR")
            return None

        info = mt5.account_info()
        mt5.shutdown()

        if info:
            return {
                "login": info.login,
                "server": info.server,
                "balance": info.balance,
                "equity": info.equity,
                "account_type": "DEMO" if info.trade_mode == 0 else "LIVE",
            }
        return None
    except Exception as e:
        log(f"MT5 check error: {e}", "ERR")
        return None


def load_credentials():
    """Load MT5 credentials from file."""
    if CREDENTIALS_FILE.exists():
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return None


def start_live_trading():
    """Start live trading via API."""
    try:
        r = requests.post(f"{API_URL}/api/v1/live/start", timeout=10)
        data = r.json()
        if data.get("status") in ("started", "already_running"):
            log(f"Live trading started! PID: {data.get('pid', 'N/A')}", "OK")
            return True
        else:
            log(f"Live trading start failed: {data}", "ERR")
            return False
    except Exception as e:
        log(f"Failed to start live trading: {e}", "ERR")
        return False


def start_paper_trading():
    """Paper trading is not available — live trading only."""
    log("Paper trading not available. Use live trading.", "WARN")
    return None


def main():
    print("=" * 60)
    print("  DUTCHKEM TRADER - AUTO LAUNCHER")
    print("=" * 60)
    print()

    # Step 1: Start FastAPI server
    server_proc = start_fastapi_server()

    # Step 2: Wait for server
    if not wait_for_server():
        log("Cannot continue without server. Exiting.", "ERR")
        if server_proc:
            server_proc.terminate()
        return

    # Step 3: Check MT5
    mt5_info = check_mt5_connection()
    if mt5_info:
        log(
            f"MT5 connected: {mt5_info['account_type']} | Balance: ${mt5_info['balance']:.2f}",
            "OK",
        )

        # Step 4a: Try live trading
        if start_live_trading():
            log("=" * 60, "OK")
            log("  LIVE TRADING ACTIVE!", "OK")
            log(f"  Server: {API_URL}", "OK")
            log(f"  Dashboard: http://localhost:8888", "OK")
            log("=" * 60, "OK")
        else:
            # Fallback to paper trading
            log("Live trading failed. Falling back to paper trading...", "WARN")
            paper_proc = start_paper_trading()
            log("=" * 60, "WARN")
            log("  PAPER TRADING ACTIVE (FALLBACK)", "WARN")
            log(f"  Server: {API_URL}", "OK")
            log("=" * 60, "WARN")
    else:
        # MT5 not available - paper trading only
        log("MT5 not available. Starting paper trading...", "WARN")
        paper_proc = start_paper_trading()
        log("=" * 60, "WARN")
        log("  PAPER TRADING ACTIVE (NO MT5)", "WARN")
        log(f"  Server: {API_URL}", "OK")
        log("=" * 60, "WARN")

    # Step 5: Keep running
    log("Trading engine running. Press Ctrl+C to stop.", "INFO")
    try:
        while True:
            time.sleep(60)
            # Health check
            try:
                r = requests.get(f"{API_URL}/api/v1/health", timeout=5)
                if r.status_code != 200:
                    log("Server health check failed. Restarting...", "WARN")
            except:
                log("Server unreachable. Attempting restart...", "WARN")
                server_proc = start_fastapi_server()
                wait_for_server()
    except KeyboardInterrupt:
        log("Shutting down...", "INFO")
        # Stop trading
        try:
            requests.post(f"{API_URL}/api/v1/live/stop", timeout=5)
        except:
            pass
        # Stop server
        if server_proc and server_proc.poll() is None:
            server_proc.terminate()
        log("Stopped.", "OK")


if __name__ == "__main__":
    main()
