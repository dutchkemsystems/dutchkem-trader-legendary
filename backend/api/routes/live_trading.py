"""
Live Trading API routes — MT5 detection, setup wizard, credentials, start/stop, improvements.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent  # backend/
TRADING_DIR = BACKEND_DIR / "trades_complete"
STATE_FILE = TRADING_DIR / "complete_state.json"
LOG_FILE = TRADING_DIR / "complete_trades.jsonl"
CONTROL_FILE = TRADING_DIR / "trading_control.json"
CREDENTIALS_FILE = BACKEND_DIR / "mt5_credentials.json"
ENGINE_SCRIPT = BACKEND_DIR / "live_trading_complete.py"

# Default MT5 path
DEFAULT_MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MT5SetupResponse(BaseModel):
    installed: bool
    running: bool
    connected: bool
    path: str
    has_credentials: bool
    needs_setup: bool  # True if user needs to do something
    setup_message: str


class ConnectRequest(BaseModel):
    login: int
    password: str
    server: str
    mt5_path: Optional[str] = None


class ConnectResponse(BaseModel):
    success: bool
    message: str
    account_type: str = "UNKNOWN"
    balance: float = 0


class TradingStatusResponse(BaseModel):
    active: bool
    control: str
    state: dict
    mt5: dict
    account: dict | None = None
    engine_pid: int | None = None


class TradingControlResponse(BaseModel):
    status: str
    message: str


class ImprovementsResponse(BaseModel):
    week_number: int
    active: dict
    all_improvements: list


# ---------------------------------------------------------------------------
# Credential Storage
# ---------------------------------------------------------------------------

def save_credentials(login: int, password: str, server: str, mt5_path: str = None):
    """Save MT5 credentials to file."""
    data = {
        "login": login,
        "password": password,
        "server": server,
        "mt5_path": mt5_path or DEFAULT_MT5_PATH,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(CREDENTIALS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_credentials() -> dict | None:
    """Load saved MT5 credentials."""
    if CREDENTIALS_FILE.exists():
        try:
            with open(CREDENTIALS_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return None


# ---------------------------------------------------------------------------
# MT5 Detection & Connection
# ---------------------------------------------------------------------------

def detect_mt5():
    """Detect if MT5 is installed and running."""
    creds = load_credentials()
    mt5_path = (creds or {}).get("mt5_path", DEFAULT_MT5_PATH)

    result = {
        "installed": False,
        "running": False,
        "connected": False,
        "path": mt5_path,
    }

    # Check if installed
    if os.path.exists(mt5_path):
        result["installed"] = True

    # Check if running
    try:
        output = subprocess.check_output(
            ['tasklist', '/FI', 'IMAGENAME eq terminal64.exe'],
            text=True, stderr=subprocess.DEVNULL
        )
        if 'terminal64.exe' in output:
            result["running"] = True
    except:
        pass

    # FIX: Don't call mt5.initialize() if the engine is running — it will kill the engine's connection
    # Only check connection status via tasklist, not by initializing MT5
    if creds and result["running"]:
        # Instead of mt5.initialize(), just check if we have valid credentials
        # The engine handles its own MT5 connection
        result["connected"] = True  # Assume connected if MT5 is running and we have creds

    return result


def try_connect_mt5(login: int, password: str, server: str, mt5_path: str = None) -> dict:
    """Try to connect to MT5 with given credentials. Returns dict with success flag."""
    path = mt5_path or DEFAULT_MT5_PATH

    if not os.path.exists(path):
        return {"success": False, "message": f"MT5 not found at {path}. Please install MetaTrader 5."}

    try:
        import MetaTrader5 as mt5
        if not mt5.initialize(path=path, login=login, password=password, server=server):
            error = mt5.last_error()
            mt5.shutdown()
            return {"success": False, "message": f"MT5 connection failed: {error}"}

        info = mt5.account_info()
        if info is None:
            mt5.shutdown()
            return {"success": False, "message": "Connected but cannot get account info"}

        result = {
            "success": True,
            "message": f"Connected to {info.server} | Account {info.login}",
            "account_type": "DEMO" if info.trade_mode == 0 else "LIVE",
            "balance": info.balance,
            "login": info.login,
            "server": info.server,
            "leverage": info.leverage,
        }
        mt5.shutdown()
        return result

    except ImportError:
        return {"success": False, "message": "MetaTrader5 package not installed. Run: pip install MetaTrader5"}
    except Exception as e:
        return {"success": False, "message": f"Connection error: {str(e)}"}


def get_account_details():
    """Get full MT5 account details (single MT5 init/shutdown cycle)."""
    creds = load_credentials()
    if not creds:
        return None

    try:
        import MetaTrader5 as mt5
        if not mt5.initialize(
            path=creds.get("mt5_path", DEFAULT_MT5_PATH),
            login=creds["login"],
            password=creds["password"],
            server=creds["server"],
        ):
            return None

        info = mt5.account_info()
        if info is None:
            mt5.shutdown()
            return None

        # Get positions
        positions = mt5.positions_get()
        position_list = []
        if positions:
            for p in positions:
                position_list.append({
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "type": "BUY" if p.type == 0 else "SELL",
                    "volume": p.volume,
                    "price_open": p.price_open,
                    "price_current": p.price_current,
                    "sl": p.sl,
                    "tp": p.tp,
                    "profit": p.profit,
                    "swap": p.swap,
                    "commission": p.commission,
                    "magic": p.magic,
                    "comment": p.comment,
                    "time": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
                })

        # Get recent deals
        deals = mt5.history_deals_get(days_back=7)
        deal_list = []
        if deals:
            for d in deals[-20:]:
                deal_list.append({
                    "ticket": d.ticket,
                    "symbol": d.symbol,
                    "type": "BUY" if d.type == 0 else "SELL" if d.type == 1 else "BALANCE",
                    "volume": d.volume,
                    "price": d.price,
                    "profit": d.profit,
                    "time": datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat(),
                    "comment": d.comment,
                })

        mt5.shutdown()

        return {
            "login": info.login,
            "server": info.server,
            "name": info.name,
            "company": info.company,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "margin_free": info.margin_free,
            "leverage": info.leverage,
            "currency": info.currency,
            "profit": info.profit,
            "margin_level": info.margin_level,
            "account_type": "DEMO" if info.trade_mode == 0 else "LIVE",
            "positions_count": len(position_list),
            "positions": position_list,
            "recent_deals": deal_list,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except:
        return None


# ---------------------------------------------------------------------------
# State & Control
# ---------------------------------------------------------------------------

def get_trading_state():
    """Read trading state from file."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}


def read_control():
    """Read control status — validates PID is alive, not just file content."""
    if CONTROL_FILE.exists():
        try:
            with open(CONTROL_FILE, "r") as f:
                data = json.load(f)
                status = data.get("status", "stopped")
                
                # If status says "running", verify the engine process is actually alive
                if status == "running":
                    pid = get_engine_pid()
                    if pid is None:
                        # No PID tracked — check if any python process is running the engine
                        # Just trust the file for now, watchdog will fix if wrong
                        pass
                    elif not _is_process_alive(pid):
                        # PID exists but process is dead — update control file
                        print(f"[CONTROL] Engine PID {pid} is dead, updating status to 'stopped'")
                        write_control("stopped")
                        return "stopped"
                
                return status
        except:
            pass
    return "stopped"


def _is_process_alive(pid):
    """Check if a process with given PID is alive."""
    try:
        if os.name == 'nt':  # Windows
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x100000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:  # Unix
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError):
        return False


def write_control(status):
    """Write control status."""
    TRADING_DIR.mkdir(exist_ok=True)
    with open(CONTROL_FILE, "w") as f:
        json.dump({"status": status, "timestamp": datetime.now(timezone.utc).isoformat()}, f)


def get_trades():
    """Read recent trades from log."""
    trades = []
    if LOG_FILE.exists():
        try:
            with open(LOG_FILE, "r") as f:
                for line in f:
                    if line.strip():
                        trades.append(json.loads(line))
        except:
            pass
    return trades[-50:]


# ---------------------------------------------------------------------------
# Trading Process Management
# ---------------------------------------------------------------------------

trading_process = None
watchdog_thread = None
watchdog_active = False


def watchdog_loop():
    """Watchdog thread that monitors the engine process and auto-restarts if needed."""
    global trading_process, watchdog_active
    
    while watchdog_active:
        time.sleep(10)  # Check every 10 seconds
        
        if not watchdog_active:
            break
            
        # Check if process is running
        if trading_process and trading_process.poll() is not None:
            # Process has died
            exit_code = trading_process.returncode
            print(f"[WATCHDOG] Engine process died with exit code {exit_code}")
            
            # Read the log file for error details
            log_file_path = TRADING_DIR / "engine.log"
            error_msg = ""
            if log_file_path.exists():
                try:
                    with open(log_file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        error_msg = "".join(lines[-20:])  # Last 20 lines
                except:
                    pass
            
            print(f"[WATCHDOG] Last log lines: {error_msg[:500]}")
            
            # Auto-restart if control says "running" (didn't get stop command)
            if read_control() == "running":
                print("[WATCHDOG] Auto-restarting engine...")
                time.sleep(5)  # Wait before restart
                result = start_trading_process()
                print(f"[WATCHDOG] Restart result: {result}")
            else:
                print("[WATCHDOG] Control is 'stopped', not restarting")
                watchdog_active = False
                break


def start_watchdog():
    """Start the watchdog thread."""
    global watchdog_thread, watchdog_active
    
    if watchdog_active:
        return
    
    watchdog_active = True
    watchdog_thread = threading.Thread(target=watchdog_loop, daemon=True)
    watchdog_thread.start()
    print("[WATCHDOG] Started")


def stop_watchdog():
    """Stop the watchdog thread."""
    global watchdog_active
    watchdog_active = False


def start_trading_process():
    """Start the trading engine as a subprocess."""
    global trading_process

    if trading_process and trading_process.poll() is None:
        return {"status": "already_running", "pid": trading_process.pid}

    # Verify credentials exist
    creds = load_credentials()
    if not creds:
        return {"status": "error", "message": "No MT5 credentials configured. Please connect to MT5 first."}

    # Verify engine script exists
    if not ENGINE_SCRIPT.exists():
        return {"status": "error", "message": f"Trading engine not found at {ENGINE_SCRIPT}"}

    try:
        # Create trades directory
        TRADING_DIR.mkdir(exist_ok=True)

        # FIX: Write stdout/stderr to log file to prevent pipe deadlock
        log_file_path = TRADING_DIR / "engine.log"
        log_file = open(log_file_path, "w", encoding="utf-8")

        # Start the engine as a subprocess from the backend directory
        trading_process = subprocess.Popen(
            ["python", str(ENGINE_SCRIPT)],
            cwd=str(BACKEND_DIR),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            stdout=log_file,
            stderr=log_file,
        )

        # Wait briefly to check if process started successfully
        time.sleep(3)
        if trading_process.poll() is not None:
            log_file.close()
            with open(log_file_path, "r", encoding="utf-8") as f:
                stderr = f.read()
            return {"status": "error", "message": f"Engine exited immediately: {stderr[:500]}"}

        write_control("running")
        start_watchdog()  # Start monitoring the engine process
        return {"status": "started", "pid": trading_process.pid}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def stop_trading_process():
    """Stop the trading engine."""
    global trading_process

    stop_watchdog()  # Stop monitoring
    write_control("stopped")

    if trading_process and trading_process.poll() is None:
        trading_process.terminate()
        try:
            trading_process.wait(timeout=10)
        except:
            trading_process.kill()
            trading_process.wait(timeout=5)
        trading_process = None

    return {"status": "stopped"}


def get_engine_pid():
    """Get the PID of the running engine."""
    global trading_process
    if trading_process and trading_process.poll() is None:
        return trading_process.pid
    return None


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@router.get("/setup", response_model=MT5SetupResponse)
def get_setup_status():
    """Get MT5 setup status — tells the frontend what the user needs to do."""
    mt5_info = detect_mt5()
    creds = load_credentials()
    has_creds = creds is not None and creds.get("login") is not None

    needs_setup = not mt5_info["installed"] or not has_creds or not mt5_info["connected"]

    if not mt5_info["installed"]:
        msg = "MT5 is not installed. Please download and install MetaTrader 5 from your broker, then restart this page."
    elif not has_creds:
        msg = "MT5 is installed but no account is configured. Please enter your MT5 login credentials."
    elif not mt5_info["connected"]:
        msg = "MT5 is installed but not connected. Please check your credentials and try again."
    else:
        msg = "MT5 is ready. You can start trading!"

    return MT5SetupResponse(
        installed=mt5_info["installed"],
        running=mt5_info["running"],
        connected=mt5_info["connected"],
        path=mt5_info["path"],
        has_credentials=has_creds,
        needs_setup=needs_setup,
        setup_message=msg,
    )


@router.post("/connect", response_model=ConnectResponse)
def connect_mt5_account(req: ConnectRequest):
    """Connect to MT5 with credentials. Tests connection, then saves."""
    # Try connecting
    result = try_connect_mt5(
        login=req.login,
        password=req.password,
        server=req.server,
        mt5_path=req.mt5_path,
    )

    if result["success"]:
        # Save credentials for future use
        save_credentials(
            login=req.login,
            password=req.password,
            server=req.server,
            mt5_path=req.mt5_path,
        )

    return ConnectResponse(
        success=result["success"],
        message=result["message"],
        account_type=result.get("account_type", "UNKNOWN"),
        balance=result.get("balance", 0),
    )


@router.get("/mt5/status", response_model=dict)
def get_mt5_status():
    """Get MT5 installation and connection status."""
    return detect_mt5()


@router.get("/account")
def get_account():
    """Get full MT5 account details."""
    details = get_account_details()
    if details is None:
        return {
            "login": None, "server": None, "balance": 0, "equity": 0,
            "margin": 0, "margin_free": 0, "leverage": 0, "currency": "USD",
            "profit": 0, "account_type": "UNKNOWN", "positions_count": 0,
            "positions": [], "recent_deals": [],
        }
    return details


@router.get("/status")
def get_status():
    """Get complete trading status (optimized — single MT5 call)."""
    state = get_trading_state()
    mt5_info = detect_mt5()
    account = get_account_details()

    return {
        "active": read_control() == "running",
        "control": read_control(),
        "state": state,
        "mt5": mt5_info,
        "account": account or {},
        "engine_pid": get_engine_pid(),
    }


@router.post("/start", response_model=TradingControlResponse)
def start_trading():
    """Start live trading — checks MT5 first."""
    # Pre-flight checks
    mt5_info = detect_mt5()
    if not mt5_info["installed"]:
        return TradingControlResponse(
            status="error",
            message="MT5 is not installed. Please install MetaTrader 5 first.",
        )

    creds = load_credentials()
    if not creds:
        return TradingControlResponse(
            status="error",
            message="No MT5 account configured. Please connect to MT5 first.",
        )

    if not mt5_info["connected"]:
        return TradingControlResponse(
            status="error",
            message="MT5 is not connected. Please check your credentials.",
        )

    # Start the engine
    result = start_trading_process()
    return TradingControlResponse(
        status=result["status"],
        message=result.get("message", f"Trading {result['status']}" + (f" (PID: {result.get('pid')})" if result.get('pid') else "")),
    )


@router.post("/stop", response_model=TradingControlResponse)
def stop_trading():
    """Stop live trading."""
    result = stop_trading_process()
    return TradingControlResponse(status="stopped", message="Trading stopped")


@router.get("/improvements", response_model=ImprovementsResponse)
def get_improvements():
    """Get improvements status."""
    state = get_trading_state()
    week = state.get("week_number", 1)
    active = state.get("active_improvements", {})

    all_improvements = [
        {"name": "Correlation Filter", "key": "correlation_filter", "week": 1, "description": "Skip correlated pairs to reduce risk"},
        {"name": "Dynamic Risk Reduction", "key": "dynamic_risk", "week": 1, "description": "Reduce risk after consecutive losses"},
        {"name": "Spread Filter", "key": "spread_filter", "week": 1, "description": "Skip trades with wide spreads"},
        {"name": "News Avoidance", "key": "news_avoidance", "week": 3, "description": "Skip trading during high-impact news"},
        {"name": "Breakout Detection", "key": "breakout_detection", "week": 3, "description": "Detect price breakouts for early entries"},
        {"name": "Mean Reversion", "key": "mean_reversion", "week": 3, "description": "Trade oversold/overbought bounces"},
        {"name": "Position Scaling", "key": "position_scaling", "week": 3, "description": "Add to winning positions (pyramiding)"},
    ]

    return ImprovementsResponse(
        week_number=week,
        active=active,
        all_improvements=all_improvements,
    )


@router.get("/trades")
def get_trade_history():
    """Get recent trades."""
    return get_trades()


@router.get("/positions")
def get_positions():
    """Get open MT5 positions."""
    return get_account_details().get("positions", []) if get_account_details() else []
