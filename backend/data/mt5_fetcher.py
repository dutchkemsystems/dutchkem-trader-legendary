"""Shared MT5 real-time data fetcher.

Fetches candles and ticks from MetaTrader 5 for use across all routes.
Falls back gracefully if MT5 is unavailable.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logger.warning("MetaTrader5 package not installed — MT5 data unavailable")

_CREDENTIALS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mt5_credentials.json")


def _load_credentials() -> Optional[dict]:
    try:
        with open(_CREDENTIALS_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Cannot load MT5 credentials: %s", e)
        return None


def _init_mt5() -> bool:
    if not MT5_AVAILABLE:
        return False
    creds = _load_credentials()
    if not creds:
        return False
    path = creds.get("mt5_path", r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe")
    login = creds.get("login")
    password = creds.get("password")
    server = creds.get("server")
    if not all([login, password, server]):
        logger.warning("MT5 credentials incomplete")
        return False
    ok = mt5.initialize(path=path, login=int(login), password=password, server=server)
    if not ok:
        logger.warning("MT5 initialize failed: %s", mt5.last_error())
    return ok


def _shutdown_mt5():
    if MT5_AVAILABLE:
        mt5.shutdown()


def fetch_mt5_candles(symbol: str, timeframe: str = "H1", count: int = 200) -> Optional[pd.DataFrame]:
    """Fetch candles from MT5 synchronously. Returns None on failure."""
    if not MT5_AVAILABLE:
        return None
    tf_map = {
        "1M": mt5.TIMEFRAME_M1, "5M": mt5.TIMEFRAME_M5, "15M": mt5.TIMEFRAME_M15,
        "1H": mt5.TIMEFRAME_H1, "4H": mt5.TIMEFRAME_H4, "1D": mt5.TIMEFRAME_D1,
        "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1,
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
    }
    mt5_tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_H1)
    if not _init_mt5():
        return None
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, count)
        if rates is None or len(rates) == 0:
            logger.warning("MT5 returned no rates for %s", symbol)
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.rename(columns={"time": "timestamp", "tick_volume": "volume"})
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        df = df.set_index("timestamp")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception as e:
        logger.warning("MT5 fetch failed: %s", e)
        return None
    finally:
        _shutdown_mt5()


def fetch_mt5_price(symbol: str) -> Optional[dict]:
    """Fetch current bid/ask from MT5."""
    if not MT5_AVAILABLE:
        return None
    if not _init_mt5():
        return None
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "spread": tick.ask - tick.bid,
            "last": tick.last,
            "timestamp": datetime.fromtimestamp(tick.time, tz=timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning("MT5 price fetch failed: %s", e)
        return None
    finally:
        _shutdown_mt5()


async def async_fetch_mt5_candles(symbol: str, timeframe: str = "H1", count: int = 200) -> Optional[pd.DataFrame]:
    """Async wrapper for MT5 candle fetch (runs sync MT5 calls in a thread)."""
    try:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, fetch_mt5_candles, symbol, timeframe, count),
            timeout=10.0,
        )
    except Exception as e:
        logger.warning("Async MT5 fetch failed: %s", e)
        return None


async def async_fetch_mt5_price(symbol: str) -> Optional[dict]:
    """Async wrapper for MT5 price fetch."""
    try:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, fetch_mt5_price, symbol),
            timeout=10.0,
        )
    except Exception as e:
        logger.warning("Async MT5 price fetch failed: %s", e)
        return None
