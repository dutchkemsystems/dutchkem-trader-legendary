"""Scalping Engine — runs scalping strategies parallel to the main engine.

Called from UnifiedEngine.run() every cycle.
Does NOT block the main engine — runs asynchronously.
"""

import logging
import MetaTrader5 as mt5
from typing import Dict, List, Optional
from datetime import datetime

from .base import ScalpingStrategy, ScalpSignal
from .config import SCALPING_STRATEGIES, SCALPING_GLOBAL_CONFIG, is_any_strategy_enabled
from .strategies import ALL_STRATEGIES

logger = logging.getLogger(__name__)


class ScalpingEngine:
    """Runs scalping strategies in parallel with the main engine.
    
    Integration point: Called from UnifiedEngine.run() every cycle.
    Does NOT block the main engine — runs asynchronously.
    """
    
    def __init__(self, mt5_client, risk_manager):
        self.mt5_client = mt5_client
        self.risk_manager = risk_manager
        self.strategies: Dict[str, ScalpingStrategy] = {}
        self.trade_history: List[dict] = []
        self._load_strategies()
    
    def _load_strategies(self):
        """Dynamically load strategies based on feature flags."""
        for name, strategy_class in ALL_STRATEGIES.items():
            config = SCALPING_STRATEGIES.get(name, {})
            if config.get('enabled', False):
                self.strategies[name] = strategy_class(config)
                logger.info(f"Loaded scalping strategy: {name}")
    
    def reload_strategies(self):
        """Hot-reload strategies from config (call each cycle)."""
        self.strategies.clear()
        self._load_strategies()
    
    def run_cycle(self, symbols: List[str]):
        """Main entry point — called every cycle by UnifiedEngine.
        
        Flow:
        1. Check if any strategy is enabled
        2. Check session filter (London/NY only)
        3. Check daily loss limit
        4. For each enabled strategy:
           a. Fetch required timeframe data
           b. Call strategy.analyze()
           c. Validate signal
           d. Pass to RiskManager for approval
           e. Execute if approved
        """
        if not is_any_strategy_enabled():
            return
        
        if not self._is_session_active():
            return
        
        # Check daily loss limit using RiskManager's daily_pnl
        balance = getattr(self.risk_manager, 'balance', 10000.0)
        daily_pnl = getattr(self.risk_manager, 'daily_pnl', 0.0)
        daily_pnl_pct = (daily_pnl / balance * 100) if balance > 0 else 0.0
        if daily_pnl_pct <= -SCALPING_GLOBAL_CONFIG['daily_loss_limit_pct']:
            logger.warning("Scalping: Daily loss limit reached. Pausing.")
            return
        
        # Hot-reload in case config changed via API toggle
        self.reload_strategies()
        
        for name, strategy in self.strategies.items():
            try:
                self._run_strategy(strategy, symbols)
            except Exception as e:
                logger.error(f"Scalping strategy {name} error: {e}")
    
    def _run_strategy(self, strategy: ScalpingStrategy, symbols: List[str]):
        """Run a single strategy across all symbols."""
        for symbol in symbols:
            # Fetch data for required timeframes
            data = {}
            for tf in strategy.required_timeframes():
                data[tf] = self.mt5_client.fetch_candles(symbol, tf, 200)
            
            # Generate signal
            signal = strategy.analyze(symbol, data)
            
            if signal is None:
                continue
            
            # Validate
            if not strategy.validate_signal(signal):
                continue
            
            # Risk manager check
            if not self._check_risk(signal):
                continue
            
            # Execute
            self._execute_signal(signal)
    
    def _check_risk(self, signal: ScalpSignal) -> bool:
        """Pass signal through RiskManager checks."""
        try:
            # Spread check (via MT5 directly)
            if not self._check_spread(signal.symbol):
                return False
            # Correlation check
            if not self.risk_manager.check_correlation(signal.symbol):
                return False
            # Portfolio limits
            if not self.risk_manager.check_portfolio_limits():
                return False
            # Circuit breaker
            if not self.risk_manager.check_circuit_breaker():
                return False
            return True
        except Exception as e:
            logger.error(f"Risk check failed for {signal.symbol}: {e}")
            return False
    
    def _check_spread(self, symbol: str) -> bool:
        """Check if spread is acceptable for scalping. Returns True if OK."""
        try:
            info = mt5.symbol_info(symbol)
            if info is None:
                return False
            spread = info.spread
            point = info.point if info.point else 0.0001
            spread_pips = spread * point * 10
            max_spread = 1.5  # Scalping needs tight spreads
            if spread_pips > max_spread:
                logger.debug(f"SPREAD FILTER {symbol}: {spread_pips:.1f} pips > max {max_spread:.1f}")
                return False
            return True
        except Exception:
            return False
    
    def _execute_signal(self, signal: ScalpSignal):
        """Execute approved signal via MT5."""
        # Calculate position size: risk-based sizing
        lots = self._calculate_scalping_lots(signal)
        if lots <= 0:
            return
        
        # Get current price for SL/TP calculation
        tick = mt5.symbol_info_tick(signal.symbol)
        if tick is None:
            return
        
        info = mt5.symbol_info(signal.symbol)
        if info is None:
            return
        
        point = info.point if info.point else 0.0001
        price = tick.ask if signal.direction.value == "BUY" else tick.bid
        
        # Convert pips to price levels
        sl_distance = signal.sl_pips * point * 10
        tp_distance = signal.tp_pips * point * 10
        
        if signal.direction.value == "BUY":
            sl = price - sl_distance
            tp = price + tp_distance
        else:
            sl = price + sl_distance
            tp = price - tp_distance
        
        # Place order with unique magic
        result = self.mt5_client.place_order(
            symbol=signal.symbol,
            action=signal.direction.value,
            lots=lots,
            sl=sl,
            tp=tp,
            magic=SCALPING_GLOBAL_CONFIG['magic_base'] + self._strategy_index(signal.strategy_name),
        )
        
        # Log trade
        self._log_trade(signal, result, lots)
    
    def _calculate_scalping_lots(self, signal: ScalpSignal) -> float:
        """Calculate position size for scalping (risk-based, simplified)."""
        try:
            balance = getattr(self.risk_manager, 'balance', 10000.0)
            risk_pct = SCALPING_GLOBAL_CONFIG.get('risk_per_trade_pct', 0.5) / 100
            risk_amount = balance * risk_pct
            
            # Get point value for pip calculation
            info = mt5.symbol_info(signal.symbol)
            if info is None:
                return 0.01
            
            point = info.point if info.point else 0.0001
            tick_value = info.trade_tick_value if info.trade_tick_value else 1.0
            
            # Calculate SL in price terms
            sl_distance = signal.sl_pips * point * 10
            
            # Lots = risk_amount / (sl_distance * tick_value_per_point)
            if sl_distance > 0 and tick_value > 0:
                contract_size = info.trade_contract_size if info.trade_contract_size else 100000
                sl_value_per_lot = sl_distance * contract_size
                lots = risk_amount / sl_value_per_lot if sl_value_per_lot > 0 else 0.01
            else:
                lots = 0.01
            
            # Clamp to min/max
            min_lot = info.volume_min if info.volume_min else 0.01
            max_lot = info.volume_max if info.volume_max else 100.0
            lots = max(min_lot, min(lots, max_lot))
            
            # Round to lot step
            lot_step = info.volume_step if info.volume_step else 0.01
            lots = round(lots / lot_step) * lot_step
            
            return round(lots, 2)
        except Exception as e:
            logger.error(f"Position sizing error: {e}")
            return 0.01
    
    def _is_session_active(self) -> bool:
        """Check if current time is within allowed trading sessions."""
        now = datetime.utcnow().strftime('%H:%M')
        for session in SCALPING_GLOBAL_CONFIG['sessions']:
            if session['start'] <= now <= session['end']:
                return True
        return False
    
    def _strategy_index(self, name: str) -> int:
        """Get index for magic number offset."""
        names = list(ALL_STRATEGIES.keys())
        return names.index(name) if name in names else 0
    
    def _log_trade(self, signal, result, lots):
        """Log trade to history."""
        self.trade_history.append({
            'strategy': signal.strategy_name,
            'symbol': signal.symbol,
            'direction': signal.direction.value,
            'entry': signal.entry_price,
            'lots': lots,
            'sl_pips': signal.sl_pips,
            'tp_pips': signal.tp_pips,
            'ticket': result if result else None,
            'status': 'open',
            'pnl': 0.0,
        })
    
    def get_trade_results(self) -> List[dict]:
        """Return completed trades for sync to main engine."""
        return [t for t in self.trade_history if t.get('status') == 'closed']
