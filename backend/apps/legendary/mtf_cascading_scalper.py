"""
MTF Cascading Scalper — Multi-Timeframe Cascading Signal Alignment
==================================================================
Scans groups of 3 timeframes for directional alignment.
Executes scalp trades when all 3 timeframes agree on direction.

Signal computation: RSI + SMA20/50 + MACD crossover (sync, no LLM).
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
}

BARS_PER_SIGNAL = 100
MT5_MAGIC = 20260911
MT5_SLIPPAGE = 10


def _compute_rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return float(val) if not pd.isna(val) else 50.0


def _compute_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> float:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    return float(macd_line.iloc[-1])


class MTFCascadingScalper:
    """Multi-Timeframe Cascading Scalper.

    Scans groups of 3 timeframes for directional alignment.
    Executes scalp trades when all 3 timeframes agree on direction.
    """

    def __init__(self, mt5_engine, risk_manager, config: dict):
        self.mt5_engine = mt5_engine
        self.risk_manager = risk_manager
        self.config = config
        self.open_scalps: Dict[int, dict] = {}  # ticket -> scalp info
        self.trade_history: List[dict] = []
        self.last_scan: Optional[str] = None
        self.total_trades = 0
        self.last_error: Optional[str] = None

    # ── Main Entry Point ────────────────────────────────────────

    def scan_and_execute(self) -> Optional[dict]:
        """Scan all groups for alignment, execute if found."""
        if not self.config.get("mtf_cascading_scalper_enabled", False):
            return None

        if not self._check_safety():
            return None

        symbol = self.config.get("scalper_symbol", "EURUSD")
        groups = self.config.get("scalper_groups", [])
        restart_from_g1 = self.config.get("scalper_restart_from_group1", True)

        self.last_scan = datetime.now(timezone.utc).isoformat()

        for group in groups:
            signals = self._get_signals_for_group(symbol, group)
            alignment = self._check_alignment(signals)

            if alignment and alignment != "HOLD":
                entry_price = self._get_current_price(symbol, alignment)
                if entry_price is None:
                    continue

                result = self._execute_scalp(symbol, alignment, group["timeframes"][0], entry_price)
                if result is not None:
                    return result

            if restart_from_g1:
                break  # Only scan first group, restart on next cycle

        return None

    # ── Signal Computation ──────────────────────────────────────

    def _compute_directional_signal(self, df: pd.DataFrame) -> str:
        """Compute directional signal from OHLCV data using RSI + SMA + MACD."""
        if df is None or len(df) < 60:
            return "HOLD"

        close = df["close"]

        rsi = _compute_rsi(close, 14)
        sma20 = close.rolling(20).mean().iloc[-1]
        sma50 = close.rolling(50).mean().iloc[-1]
        macd = _compute_macd(close)

        bull_score = 0
        if rsi < 70:
            bull_score += 1  # not overbought
        if close.iloc[-1] > sma20:
            bull_score += 1
        if sma20 > sma50:
            bull_score += 1
        if macd > 0:
            bull_score += 1

        if bull_score >= 3:
            return "BUY"
        elif bull_score <= 1:
            return "SELL"
        return "HOLD"

    def _get_signals_for_group(self, symbol: str, group: dict) -> List[str]:
        """Fetch OHLCV for all timeframes in a group and compute signals."""
        timeframes = group.get("timeframes", [])
        signals = []
        for tf in timeframes:
            df = self._fetch_ohlcv(symbol, tf)
            signal = self._compute_directional_signal(df)
            signals.append(signal)
        return signals

    def _check_alignment(self, signals: List[str]) -> Optional[str]:
        """All 3 signals same direction -> return it, else None."""
        if not signals or len(signals) < 3:
            return None
        if signals[0] == signals[1] == signals[2] and signals[0] != "HOLD":
            return signals[0]
        return None

    # ── Data Fetching ───────────────────────────────────────────

    def _fetch_ohlcv(self, symbol: str, tf: str) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data from MT5 directly."""
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        if not info.visible:
            mt5.symbol_select(symbol, True)

        mt5_tf = TIMEFRAME_MAP.get(tf)
        if mt5_tf is None:
            return None

        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, 0, BARS_PER_SIGNAL)
        if rates is None or len(rates) < 60:
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.rename(columns={"time": "timestamp", "tick_volume": "volume"})
        df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
        return df

    def _get_current_price(self, symbol: str, direction: str) -> Optional[float]:
        """Get current execution price for the given direction."""
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        if direction == "BUY":
            return tick.ask
        elif direction == "SELL":
            return tick.bid
        return None

    # ── Safety Checks ───────────────────────────────────────────

    def _check_safety(self) -> bool:
        """Session filter + drawdown + position count + RiskManager checks."""
        now = datetime.now(timezone.utc)
        session_hours = self.config.get("session_hours", set(range(7, 22)))
        if now.hour not in session_hours:
            return False

        dd_pct = self.risk_manager.get_drawdown_pct()
        dd_pause = self.config.get("drawdown_pause_pct", 0.15)
        if dd_pct >= dd_pause:
            return False

        if not self.risk_manager.check_circuit_breaker():
            return False

        max_concurrent = self.config.get("scalper_max_concurrent", 3)
        if len(self.open_scalps) >= max_concurrent:
            return False

        if not self.risk_manager.check_portfolio_limits():
            return False

        return True

    # ── Order Execution ─────────────────────────────────────────

    def _execute_scalp(self, symbol: str, direction: str, entry_tf: str, entry_price: float) -> Optional[dict]:
        """Place order with TP/SL."""
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return None

        sl, tp = self._calculate_sl_tp(entry_price, direction, symbol_info)
        lot_size = self.config.get("scalper_lot_size", 0.01)

        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type,
            "price": entry_price,
            "sl": sl,
            "tp": tp,
            "deviation": MT5_SLIPPAGE,
            "magic": MT5_MAGIC,
            "comment": "MTF_CASCADE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else "None"
            code = result.retcode if result else "N/A"
            self.last_error = f"Order failed: {err} (code={code})"
            log.error(f"SCALP FAIL: {direction} {symbol} @ {entry_price} — {err}")
            return None

        ticket = result.order
        scalp = {
            "ticket": ticket,
            "symbol": symbol,
            "direction": direction,
            "entry_price": result.price,
            "entry_time": datetime.now(timezone.utc).isoformat(),
            "entry_tf": entry_tf,
            "size": lot_size,
            "sl": sl,
            "tp": tp,
            "status": "OPEN",
        }
        self.open_scalps[ticket] = scalp
        self.total_trades += 1
        self.last_error = None

        log.info(f"SCALP OPEN: {direction} {lot_size} {symbol} @ {result.price:.5f} "
                 f"SL={sl:.5f} TP={tp:.5f} ticket={ticket}")
        return scalp

    def _calculate_sl_tp(self, price: float, action: str, symbol_info) -> Tuple[float, float]:
        """Calculate SL/TP from pips config and symbol point size."""
        point = symbol_info.point if symbol_info.point else 0.0001
        sl_pips = self.config.get("scalper_sl_pips", 10)
        tp_pips = self.config.get("scalper_tp_pips", 15)

        sl_dist = sl_pips * point * 10  # pips to price distance
        tp_dist = tp_pips * point * 10

        if action == "BUY":
            sl = round(price - sl_dist, symbol_info.digits)
            tp = round(price + tp_dist, symbol_info.digits)
        else:
            sl = round(price + sl_dist, symbol_info.digits)
            tp = round(price - tp_dist, symbol_info.digits)

        return sl, tp

    # ── Status / Dashboard ──────────────────────────────────────

    def refresh_trade_statuses(self):
        """Update open scalp statuses from MT5 positions."""
        closed = []
        for ticket, scalp in list(self.open_scalps.items()):
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                scalp["status"] = "CLOSED"
                self.trade_history.append(scalp)
                closed.append(ticket)

        for ticket in closed:
            del self.open_scalps[ticket]

    def get_status(self) -> dict:
        """Return status dict for dashboard display."""
        return {
            "enabled": self.config.get("mtf_cascading_scalper_enabled", False),
            "open_scalps": len(self.open_scalps),
            "total_trades": self.total_trades,
            "last_scan": self.last_scan,
            "last_error": self.last_error,
            "symbol": self.config.get("scalper_symbol", "EURUSD"),
            "tp_pips": self.config.get("scalper_tp_pips", 15),
            "sl_pips": self.config.get("scalper_sl_pips", 10),
            "max_concurrent": self.config.get("scalper_max_concurrent", 3),
            "groups": [
                g["name"] for g in self.config.get("scalper_groups", [])
            ],
        }
