"""Scalping Engine — runs scalping strategies parallel to the main engine.

Called from UnifiedEngine.run() every cycle.
Does NOT block the main engine — runs asynchronously.
"""

import logging
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
    
    async def run_cycle(self, symbols: List[str]):
        """Main entry point — called every 5 minutes by UnifiedEngine.
        
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
        
        if self.risk_manager.daily_pnl_pct <= -SCALPING_GLOBAL_CONFIG['daily_loss_limit_pct']:
            logger.warning("Scalping: Daily loss limit reached. Pausing.")
            return
        
        # Hot-reload in case config changed via API toggle
        self.reload_strategies()
        
        for name, strategy in self.strategies.items():
            try:
                await self._run_strategy(strategy, symbols)
            except Exception as e:
                logger.error(f"Scalping strategy {name} error: {e}")
    
    async def _run_strategy(self, strategy: ScalpingStrategy, symbols: List[str]):
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
            await self._execute_signal(signal)
    
    def _check_risk(self, signal: ScalpSignal) -> bool:
        """Pass signal through RiskManager checks."""
        checks = [
            self.risk_manager.check_spread(signal.symbol, signal.strategy_name),
            self.risk_manager.check_correlation(signal.symbol),
            self.risk_manager.check_portfolio_limits(),
            self.risk_manager.check_circuit_breaker(),
        ]
        return all(checks)
    
    async def _execute_signal(self, signal: ScalpSignal):
        """Execute approved signal via MT5."""
        # Calculate position size via RiskManager
        lots = self.risk_manager.calculate_position_size(
            signal.symbol, signal.sl_pips, signal.confidence
        )
        
        # Place order with unique magic
        result = self.mt5_client.place_order(
            symbol=signal.symbol,
            action=signal.direction.value,
            lots=lots,
            sl_pips=signal.sl_pips,
            tp_pips=signal.tp_pips,
            magic=SCALPING_GLOBAL_CONFIG['magic_base'] + self._strategy_index(signal.strategy_name),
            comment=f"SCALP_{signal.strategy_name[:8]}"
        )
        
        # Log trade
        self._log_trade(signal, result, lots)
    
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
            'ticket': result.get('ticket') if result else None,
            'status': 'open',
            'pnl': 0.0,
        })
    
    def get_trade_results(self) -> List[dict]:
        """Return completed trades for sync to main engine."""
        return [t for t in self.trade_history if t.get('status') == 'closed']
