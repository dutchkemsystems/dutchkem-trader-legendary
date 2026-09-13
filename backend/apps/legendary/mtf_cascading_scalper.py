"""
MTF Cascading Scalper — Multi-Timeframe Cascading Signal Alignment
==================================================================
Scans groups of 3 timeframes for directional alignment across multiple symbols.
Executes scalp trades when all 3 timeframes agree on direction.
Includes trailing stop management and breakeven logic.

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

WATCHLIST = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD",
    "EURJPY", "GBPJPY", "AUDJPY", "EURAUD", "EURGBP",
]


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

    Scans groups of 3 timeframes for directional alignment across multiple symbols.
    Executes scalp trades when all 3 timeframes agree on direction.
    Manages trailing stops and breakeven for open scalps.
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
        self._symbol_index: int = 0  # Round-robin index for multi-symbol scanning

    # ── Main Entry Point ────────────────────────────────────────

    def scan_and_execute(self) -> Optional[dict]:
        """Scan all symbols/groups for alignment, execute if found."""
        if not self.config.get("mtf_cascading_scalper_enabled", False):
            return None

        if not self._check_safety():
            return None

        # Manage trailing stops for existing open scalps
        self._manage_trailing_stops()

        # Get symbols to scan
        symbols = self._get_symbols_to_scan()
        if not symbols:
            return None

        # ── CROSS-DEDUP: Skip symbols blocked by main engine ──
        blocked = getattr(self, 'blocked_symbols', set())
        symbols = [s for s in symbols if s not in blocked]
        if not symbols:
            return None

        restart_from_g1 = self.config.get("scalper_restart_from_group1", True)
        prefer_groups = self.config.get("scalper_prefer_groups", [])

        # Rotate through symbols (one per scan cycle)
        symbol = symbols[self._symbol_index % len(symbols)]
        self._symbol_index += 1

        self.last_scan = datetime.now(timezone.utc).isoformat()

        # Try preferred groups first, then all groups
        all_groups = self.config.get("scalper_groups", [])
        ordered_groups = []
        if prefer_groups:
            ordered_groups = [g for g in all_groups if g["name"] in prefer_groups]
        ordered_groups.extend([g for g in all_groups if g not in ordered_groups])

        for group in ordered_groups:
            signals = self._get_signals_for_group(symbol, group)
            alignment = self._check_alignment(signals)

            if alignment and alignment != "HOLD":
                entry_price = self._get_current_price(symbol, alignment)
                if entry_price is None:
                    continue

                result = self._execute_scalp(symbol, alignment, group["name"], entry_price)
                if result is not None:
                    return result

            if restart_from_g1:
                break  # Only scan first group, restart on next cycle

        return None

    def _get_symbols_to_scan(self) -> List[str]:
        """Get list of symbols to scan. Multi-symbol uses WATCHLIST."""
        if self.config.get("scalper_multi_symbol", False):
            watchlist = self.config.get("watchlist", WATCHLIST)
            return [s for s in watchlist if s and s.strip()]
        return [self.config.get("scalper_symbol", "EURUSD")]

    # ── Trailing Stop Management ────────────────────────────────

    def _manage_trailing_stops(self):
        """Manage trailing stops and breakeven for all open scalps."""
        if not self.config.get("scalper_trailing_enabled", False):
            return

        breakeven_rr = self.config.get("scalper_trailing_breakeven_rr", 1.0)
        trail_step_pips = self.config.get("scalper_trailing_step_pips", 5)

        for ticket, scalp in list(self.open_scalps.items()):
            if scalp.get("status") != "OPEN":
                continue

            symbol = scalp["symbol"]
            direction = scalp["direction"]
            entry_price = scalp["entry_price"]
            current_sl = scalp.get("sl", 0)
            current_tp = scalp.get("tp", 0)

            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                continue

            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                continue

            point = symbol_info.point if symbol_info.point else 0.0001
            digits = symbol_info.digits

            if direction == "BUY":
                current_price = tick.bid
                # Breakeven: move SL to entry when price reaches entry + (SL distance * breakeven_rr)
                sl_distance = abs(entry_price - current_sl)
                breakeven_level = entry_price + sl_distance * breakeven_rr
                if current_price >= breakeven_level and current_sl < entry_price:
                    new_sl = round(entry_price + (point * 2), digits)  # Entry + 2 points buffer
                    self._modify_sl(ticket, new_sl)
                    scalp["sl"] = new_sl
                    scalp["breakeven_hit"] = True
                    log.info(f"SCALP BE: BUY {symbol} ticket={ticket} SL moved to {new_sl:.5f}")

                # Trailing: move SL up by trail_step_pips when price makes new high
                elif scalp.get("breakeven_hit", False) and current_price > scalp.get("last_high", 0):
                    trail_dist = trail_step_pips * point * 10
                    new_sl = round(current_price - trail_dist, digits)
                    if new_sl > current_sl:
                        self._modify_sl(ticket, new_sl)
                        scalp["sl"] = new_sl
                        scalp["last_high"] = current_price

            elif direction == "SELL":
                current_price = tick.ask
                sl_distance = abs(current_sl - entry_price)
                breakeven_level = entry_price - sl_distance * breakeven_rr
                if current_price <= breakeven_level and current_sl > entry_price:
                    new_sl = round(entry_price - (point * 2), digits)
                    self._modify_sl(ticket, new_sl)
                    scalp["sl"] = new_sl
                    scalp["breakeven_hit"] = True
                    log.info(f"SCALP BE: SELL {symbol} ticket={ticket} SL moved to {new_sl:.5f}")

                elif scalp.get("breakeven_hit", False):
                    last_low = scalp.get("last_low", 0)
                    if last_low == 0 or current_price < last_low:
                        trail_dist = trail_step_pips * point * 10
                        new_sl = round(current_price + trail_dist, digits)
                        if new_sl < current_sl:
                            self._modify_sl(ticket, new_sl)
                            scalp["sl"] = new_sl
                            scalp["last_low"] = current_price

    def _modify_sl(self, ticket: int, new_sl: float) -> bool:
        """Modify SL for an open position."""
        try:
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return False
            pos = positions[0]
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "symbol": pos.symbol,
                "sl": new_sl,
                "tp": pos.tp,
                "magic": MT5_MAGIC,
            }
            result = mt5.order_send(request)
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return True
            log.debug(f"SL modify failed: ticket={ticket} code={result.retcode if result else 'None'}")
            return False
        except Exception as e:
            log.debug(f"SL modify error: {e}")
            return False

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

    def _compute_signal_details(self, symbol: str, df: pd.DataFrame) -> dict:
        """Compute directional signal and return full indicator details."""
        if df is None or len(df) < 60:
            return {"direction": "HOLD", "rsi": 50.0, "macd": 0.0, "sma20": 0.0, "sma50": 0.0}

        close = df["close"]
        rsi = _compute_rsi(close, 14)
        sma20 = float(close.rolling(20).mean().iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1])
        macd = _compute_macd(close)

        bull_score = 0
        if rsi < 70:
            bull_score += 1
        if close.iloc[-1] > sma20:
            bull_score += 1
        if sma20 > sma50:
            bull_score += 1
        if macd > 0:
            bull_score += 1

        if bull_score >= 3:
            direction = "BUY"
        elif bull_score <= 1:
            direction = "SELL"
        else:
            direction = "HOLD"

        return {"direction": direction, "rsi": round(rsi, 2), "macd": round(macd, 6),
                "sma20": round(sma20, 5), "sma50": round(sma50, 5)}

    def _get_signals_for_group(self, symbol: str, group: dict) -> List[str]:
        """Fetch OHLCV for all timeframes in a group and compute signals."""
        timeframes = group.get("timeframes", [])
        signals = []
        for tf in timeframes:
            df = self._fetch_ohlcv(symbol, tf)
            signal = self._compute_directional_signal(df)
            signals.append(signal)
        return signals

    def _get_detailed_signals_for_group(self, symbol: str, group: dict) -> Tuple[List[str], dict, dict]:
        """Fetch OHLCV for all timeframes in a group, compute signals + indicator details.

        Returns (signals_list, tf_direction_map, last_tf_details) where last_tf_details
        has RSI/MACD/SMA values from the highest timeframe in the group.
        """
        timeframes = group.get("timeframes", [])
        signals = []
        tf_map = {}
        last_details = {"direction": "HOLD", "rsi": 50.0, "macd": 0.0, "sma20": 0.0, "sma50": 0.0}
        for tf in timeframes:
            df = self._fetch_ohlcv(symbol, tf)
            sig = self._compute_signal_details(symbol, df)
            signals.append(sig["direction"])
            tf_map[tf] = sig["direction"]
            last_details = sig
        return signals, tf_map, last_details

    def scan_all_symbols(self) -> List[dict]:
        """Scan ALL symbols across ALL groups and return quality trade candidates.

        Does NOT execute trades — returns analysis for dashboard display.
        Skips symbols that are blocked or already have open scalps.
        """
        candidates = []

        symbols = self._get_symbols_to_scan()
        blocked = getattr(self, 'blocked_symbols', set())
        symbols = [s for s in symbols if s not in blocked]

        # Symbols that already have open scalps
        open_symbols = {s["symbol"] for s in self.open_scalps.values()}

        all_groups = self.config.get("scalper_groups", [])

        for symbol in symbols:
            if symbol in open_symbols:
                continue

            # Pre-fetch symbol info once
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                continue

            for group in all_groups:
                try:
                    signals, tf_map, last_details = self._get_detailed_signals_for_group(symbol, group)
                    alignment = self._check_alignment(signals)

                    if not alignment or alignment == "HOLD":
                        continue

                    entry_price = self._get_current_price(symbol, alignment)
                    if entry_price is None:
                        continue

                    sl_pips = self.config.get("scalper_sl_pips", 5)
                    tp_pips = self.config.get("scalper_tp_pips", 10)
                    point = symbol_info.point if symbol_info.point else 0.0001
                    digits = symbol_info.digits

                    sl_dist = sl_pips * point * 10
                    tp_dist = tp_pips * point * 10

                    if alignment == "BUY":
                        sl = round(entry_price - sl_dist, digits)
                        tp = round(entry_price + tp_dist, digits)
                    else:
                        sl = round(entry_price + sl_dist, digits)
                        tp = round(entry_price - tp_dist, digits)

                    lot_size = self._select_scalper_lot_size(symbol, group["name"], alignment, entry_price, symbol_info)

                    # Pip value estimation
                    if symbol in ("XAUUSD",):
                        pip_value_per_lot = 1.0
                    elif "JPY" in symbol:
                        pip_value_per_lot = 6.67
                    else:
                        pip_value_per_lot = 10.0

                    expected_profit_usd = tp_pips * pip_value_per_lot * lot_size
                    risk_reward = round(tp_pips / sl_pips, 2) if sl_pips > 0 else 0

                    candidates.append({
                        "symbol": symbol,
                        "direction": alignment,
                        "group": group["name"],
                        "timeframes": group.get("timeframes", []),
                        "signals_per_tf": tf_map,
                        "rsi": last_details.get("rsi", 50.0),
                        "macd": last_details.get("macd", 0.0),
                        "sma20": last_details.get("sma20", 0.0),
                        "sma50": last_details.get("sma50", 0.0),
                        "entry_price": entry_price,
                        "sl": sl,
                        "tp": tp,
                        "sl_pips": sl_pips,
                        "tp_pips": tp_pips,
                        "lot_size": lot_size,
                        "expected_profit_usd": round(expected_profit_usd, 2),
                        "risk_reward": risk_reward,
                        "pip_value_per_lot": pip_value_per_lot,
                    })
                except Exception as e:
                    log.debug(f"scan_all_symbols: {symbol} {group.get('name', '?')} error: {e}")
                    continue

        log.info(f"scan_all_symbols: found {len(candidates)} candidates across {len(symbols)} symbols")
        return candidates

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

        max_concurrent = self.config.get("scalper_max_concurrent", 5)
        if len(self.open_scalps) >= max_concurrent:
            return False

        if not self.risk_manager.check_portfolio_limits():
            return False

        return True

    # ── Dynamic Lot Sizing (Strategy Selector for Scalper) ──

    def _select_scalper_lot_size(self, symbol: str, group_name: str, direction: str,
                                  entry_price: float, symbol_info) -> float:
        """Select lot size based on group timeframe strength and session context.
        
        Logic:
        - G5/G6/G7 (higher timeframes): Aggressive sizing (stronger trends)
        - G1/G2 (lower timeframes): Conservative sizing (noisier)
        - London/NY session: Aggressive bias
        - Asian/Off-peak: Conservative bias
        - Win streak: Slight aggression; Loss streak: Slight caution
        
        Returns: lot size
        """
        base_lots = self.config.get("scalper_lot_size", 0.01)

        # ── Factor 1: Group timeframe tier ──
        # G1-G2: scalp tier (M1-M30) → conservative
        # G3-G4: transition tier (M15-H4) → neutral
        # G5-G7: trend tier (H1-MN1) → aggressive
        group_tier = {
            "G1": "scalp", "G2": "scalp",
            "G3": "transition", "G4": "transition",
            "G5": "trend", "G6": "trend", "G7": "trend",
        }
        tier = group_tier.get(group_name, "transition")
        if tier == "trend":
            base_lots *= 1.5  # 50% larger for higher-TF alignment
        elif tier == "scalp":
            base_lots *= 0.7  # 30% smaller for noisy lower-TF

        # ── Factor 2: Session bias ──
        now_hour = datetime.now(timezone.utc).hour
        if now_hour in [13, 14, 15, 16]:
            base_lots *= 1.2  # London/NY overlap → 20% aggression
        elif now_hour < 7 or now_hour > 21:
            base_lots *= 0.6  # Asian/off-peak → 40% caution

        # ── Factor 3: Win/loss streak (from trade history) ──
        if len(self.trade_history) >= 3:
            recent = self.trade_history[-5:]
            wins = sum(1 for t in recent if t.get("profit", 0) > 0)
            if wins >= 4:
                base_lots *= 1.15  # Hot streak → 15% aggression
            elif wins <= 1:
                base_lots *= 0.8   # Cold streak → 20% caution

        # ── Factor 4: Symbol volatility tier ──
        # JPY pairs and Gold are more volatile → smaller size
        volatile_symbols = {"USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "XAUUSD"}
        if symbol in volatile_symbols:
            base_lots *= 0.7

        # ── Floor and cap ──
        lot_size = max(0.01, min(base_lots, self.config.get("scalper_max_lots", 0.50)))
        lot_size = round(lot_size, 2)

        # Ensure minimum lot size
        if lot_size < symbol_info.volume_min:
            lot_size = symbol_info.volume_min
        lot_size = round(lot_size / symbol_info.volume_step) * symbol_info.volume_step
        lot_size = round(lot_size, 2)

        log.info(f"SCALP SIZING: {symbol} {group_name} tier={tier} session={now_hour}UTC "
                 f"→ lots={lot_size:.2f} (base={self.config.get('scalper_lot_size', 0.01):.2f})")

        return lot_size

    # ── Order Execution ─────────────────────────────────────────

    def _execute_scalp(self, symbol: str, direction: str, group_name: str, entry_price: float) -> Optional[dict]:
        """Place order with dynamic lot sizing based on group alignment and session."""
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return None

        sl, tp = self._calculate_sl_tp(entry_price, direction, symbol_info)

        # ── Dynamic Lot Sizing (Strategy Selector for Scalper) ──
        lot_size = self._select_scalper_lot_size(symbol, group_name, direction, entry_price, symbol_info)

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
            "comment": f"MTF_{group_name}",
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
            "group": group_name,
            "size": lot_size,
            "sl": sl,
            "tp": tp,
            "status": "OPEN",
            "breakeven_hit": False,
            "last_high": result.price if direction == "BUY" else 0,
            "last_low": result.price if direction == "SELL" else 0,
            "strategy_profile": "dynamic",
        }
        self.open_scalps[ticket] = scalp
        self.total_trades += 1
        self.last_error = None

        log.info(f"SCALP OPEN: {direction} {lot_size} {symbol} @ {result.price:.5f} "
                 f"SL={sl:.5f} TP={tp:.5f} ticket={ticket} group={group_name}")
        return scalp

    def _calculate_sl_tp(self, price: float, action: str, symbol_info) -> Tuple[float, float]:
        """Calculate SL/TP from pips config and symbol point size."""
        point = symbol_info.point if symbol_info.point else 0.0001
        sl_pips = self.config.get("scalper_sl_pips", 5)
        tp_pips = self.config.get("scalper_tp_pips", 10)

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

        # Cap trade_history to prevent memory leak (keep last 200)
        if len(self.trade_history) > 200:
            self.trade_history = self.trade_history[-200:]

    def get_status(self) -> dict:
        """Return status dict for dashboard display."""
        status = {
            "enabled": self.config.get("mtf_cascading_scalper_enabled", False),
            "multi_symbol": self.config.get("scalper_multi_symbol", False),
            "open_scalps": len(self.open_scalps),
            "total_trades": self.total_trades,
            "last_scan": self.last_scan,
            "last_error": self.last_error,
            "symbol": self.config.get("scalper_symbol", "EURUSD"),
            "tp_pips": self.config.get("scalper_tp_pips", 10),
            "sl_pips": self.config.get("scalper_sl_pips", 5),
            "max_concurrent": self.config.get("scalper_max_concurrent", 5),
            "trailing_enabled": self.config.get("scalper_trailing_enabled", False),
            "prefer_groups": self.config.get("scalper_prefer_groups", []),
            "open_positions": [
                {
                    "ticket": s["ticket"],
                    "symbol": s["symbol"],
                    "direction": s["direction"],
                    "entry": s["entry_price"],
                    "sl": s["sl"],
                    "tp": s["tp"],
                    "group": s["group"],
                    "breakeven": s.get("breakeven_hit", False),
                }
                for s in self.open_scalps.values()
            ],
            "groups": [
                g["name"] for g in self.config.get("scalper_groups", [])
            ],
        }
        # Include quality trades scan result for dashboard (non-blocking)
        if self.config.get("mtf_cascading_scalper_enabled", False):
            try:
                status["quality_trades"] = self.scan_all_symbols()
            except Exception as e:
                log.debug(f"get_status quality_trades scan failed: {e}")
                status["quality_trades"] = []
        else:
            status["quality_trades"] = []
        return status
