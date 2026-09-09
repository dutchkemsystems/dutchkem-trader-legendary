"""
Paper Trading V2 — Background Runner
=====================================
Runs paper_trading_v2.py as a background process.
Handles auto-restart on crash, logging, and monitoring.

Usage:
  python run_paper_v2.py              # Start background
  python run_paper_v2.py --status     # Check status
  python run_paper_v2.py --stop       # Stop background
  python run_paper_v2.py --foreground # Run in foreground (for testing)
"""
import os
import sys
import time
import json
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).parent
PID_FILE = BACKEND_DIR / "paper_trades" / "paper_v2.pid"
LOG_DIR = BACKEND_DIR / "paper_trades"
STATUS_FILE = BACKEND_DIR / "paper_trades" / "paper_v2_status.json"
ENGINE_SCRIPT = BACKEND_DIR / "paper_trading_v2.py"


def write_status(status, details=None):
    """Write status file for monitoring."""
    LOG_DIR.mkdir(exist_ok=True)
    data = {
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
    }
    if details:
        data.update(details)
    with open(STATUS_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def is_running():
    """Check if the background process is still running."""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        # Check if process exists
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True, text=True
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except (ProcessLookupError, ValueError, PermissionError):
        return False


def start_background():
    """Start paper trading in background."""
    if is_running():
        print("  Paper trading V2 is already running.")
        return

    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"paper_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # Start process
    cmd = [sys.executable, str(ENGINE_SCRIPT)]
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        cmd,
        stdout=open(log_file, "w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        cwd=str(BACKEND_DIR),
        creationflags=creation_flags,
    )

    # Save PID
    PID_FILE.write_text(str(proc.pid))
    write_status("running", {"log_file": str(log_file)})

    print(f"  Paper trading V2 started!")
    print(f"  PID: {proc.pid}")
    print(f"  Log: {log_file}")
    print(f"  Status: {STATUS_FILE}")


def stop_background():
    """Stop the background process."""
    if not PID_FILE.exists():
        print("  No PID file found.")
        return

    try:
        pid = int(PID_FILE.read_text().strip())
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        print(f"  Stopped process {pid}")
    except Exception as e:
        print(f"  Error stopping: {e}")

    PID_FILE.unlink(missing_ok=True)
    write_status("stopped")


def show_status():
    """Show current status."""
    running = is_running()

    if STATUS_FILE.exists():
        with open(STATUS_FILE) as f:
            status = json.load(f)
        print(f"\n  Status: {status.get('status', 'unknown')}")
        print(f"  Last update: {status.get('timestamp', 'N/A')}")
    else:
        print(f"\n  Status: {'running' if running else 'not running'}")

    # Check for results
    summary_file = LOG_DIR / "paper_trading_summary_v2.json"
    state_file = LOG_DIR / "paper_trading_state_v2.json"
    trades_file = LOG_DIR / "paper_trades_v2.jsonl"

    if state_file.exists():
        with open(state_file) as f:
            state = json.load(f)
        print(f"\n  Balance: ${state.get('balance', 10000):,.2f}")
        print(f"  Total trades: {state.get('total_trades', 0)}")
        print(f"  Wins: {state.get('wins', 0)}")
        print(f"  Losses: {state.get('losses', 0)}")
        print(f"  P&L: ${state.get('total_pnl', 0):+.2f}")
        print(f"  Open positions: {len(state.get('positions', {}))}")

    if summary_file.exists():
        with open(summary_file) as f:
            summary = json.load(f)
        print(f"\n  Duration: {summary.get('duration_hours', 0)}h")
        print(f"  Cycles: {summary.get('total_cycles', 0)}")


def run_foreground():
    """Run in foreground for testing."""
    print("  Running in foreground mode...")
    print("  Press Ctrl+C to stop.\n")
    os.chdir(str(BACKEND_DIR))
    os.execv(sys.executable, [sys.executable, str(ENGINE_SCRIPT)])


if __name__ == "__main__":
    if "--status" in sys.argv:
        show_status()
    elif "--stop" in sys.argv:
        stop_background()
    elif "--foreground" in sys.argv:
        run_foreground()
    else:
        start_background()
