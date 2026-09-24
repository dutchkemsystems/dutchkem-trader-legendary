"""Gold Hedge EA — Martingale-style hedge strategy for XAUUSD.

Uses a basket management system with:
- Initial entry based on trend analysis (EMA + RSI + ATR)
- Hedge levels with increasing lot sizes (0.01 → 0.02 → 0.03 → 0.05 → 0.08)
- Basket take-profit (hard + trailing)
- Freeze loss protection
- Pending order placement via MT5Connector

Designed as a standalone module — does NOT inherit from ScalpingStrategy.
Integrates with UnifiedEngine via GoldHedgeIntegration class.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from .hedge_basket import HedgeBasketManager, BasketState

log = logging.getLogger(__name__)

# Magic numbers for Gold Hedge EA (234020-234029)
GOLD_HEDGE_MAGIC_BASE = 234020


class GoldHedgeEA:
    """Gold Hedge EA — standalone strategy for XAUUSD hedging.
    
    This class does NOT inherit from ScalpingStrategy because:
    - It requires basket management (multiple positions per signal)
    - It uses pending orders (BuyStop/SellStop)
    - It has stateful logic (basket levels, trailing TP)
    
    Instead, it exposes an `analyze()` method compatible with
    the UnifiedEngine's manual polling loop.
    """
    
    def __init__(self, config: Dict, mt5_connector=None):
        """Initialize Gold Hedge EA.
        
        Args:
            config: Strategy configuration dict
            mt5_connector: MT5Connector instance for order execution
        """
        self.config = config
        self.mt5 = mt5_connector
        self.basket_manager = HedgeBasketManager(config)
        
        # EMA parameters
        self.ema_fast = config.get('ema_fast', 20)
        self.ema_slow = config.get('ema_slow', 50)
        self.rsi_period = config.get('rsi_period', 14)
        self.atr_period = config.get('atr_period', 14)
        
        # Hedge distance (ATR multiplier)
        self.hedge_distance_atr = config.get('hedge_distance_atr', 1.5)
        
        # State
        self._last_check_time = None
        self._check_interval = config.get('check_interval_seconds', 60)
    
    def analyze(self, symbol: str, data: pd.DataFrame) -> Optional[Dict]:
        """Analyze market for Gold Hedge EA signals.
        
        Args:
            symbol: Trading symbol (should be XAUUSD)
            data: OHLCV DataFrame with M5 or M15 timeframe
            
        Returns:
            Dict with action info, or None if no action needed
        """
        if data is None or len(data) < 60:
            return None
        
        # Check if this is XAUUSD (or gold variant)
        if 'XAU' not in symbol.upper():
            return None
        
        # Calculate indicators
        close = data['close']
        ema_fast = close.ewm(span=self.ema_fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.ema_slow, adjust=False).mean()
        
        rsi = self._calculate_rsi(close, self.rsi_period)
        atr = self._calculate_atr(data, self.atr_period)
        
        current_price = close.iloc[-1]
        current_ema_fast = ema_fast.iloc[-1]
        current_ema_slow = ema_slow.iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_atr = atr.iloc[-1]
        
        # Determine trend direction
        trend = self._get_trend(current_price, current_ema_fast, current_ema_slow)
        
        # Check for hedge entry conditions
        if self.basket_manager.has_active_basket(symbol):
            return self._check_hedge_conditions(symbol, current_price, current_atr, trend)
        else:
            return self._check_initial_entry(symbol, current_price, current_rsi, current_atr, trend)
    
    def _get_trend(self, price: float, ema_fast: float, ema_slow: float) -> str:
        """Determine trend direction."""
        if price > ema_fast > ema_slow:
            return 'BUY'
        elif price < ema_fast < ema_slow:
            return 'SELL'
        return 'NEUTRAL'
    
    def _check_initial_entry(
        self, symbol: str, price: float, rsi: float, atr: float, trend: str
    ) -> Optional[Dict]:
        """Check for initial basket entry."""
        if trend == 'NEUTRAL':
            return None
        
        # Entry conditions:
        # 1. Trend confirmed (EMA alignment)
        # 2. RSI not overbought/oversold (30-70 range)
        # 3. ATR indicates sufficient volatility
        if rsi > 70 or rsi < 30:
            return None
        
        if atr < 0.5:  # Minimum ATR for gold
            return None
        
        # Place initial entry
        lots = self.config.get('lot_progression', [0.01])[0]
        
        return {
            'action': 'OPEN_BASKET',
            'direction': trend,
            'lots': lots,
            'price': price,
            'atr': atr,
            'rsi': rsi,
            'reason': f'GOLD_HEDGE: {trend} entry (RSI={rsi:.1f}, ATR={atr:.2f})',
            'magic': GOLD_HEDGE_MAGIC_BASE,
        }
    
    def _check_hedge_conditions(
        self, symbol: str, price: float, atr: float, trend: str
    ) -> Optional[Dict]:
        """Check if hedge level should be added."""
        basket = self.basket_manager.get_basket(symbol)
        if basket is None:
            return None
        
        # Check if basket should be closed
        current_pnl = self.basket_manager.calculate_basket_pnl(
            symbol, {'bid': price, 'ask': price}
        )
        should_close, reason = self.basket_manager.should_close_basket(symbol, current_pnl)
        
        if should_close:
            return {
                'action': 'CLOSE_BASKET',
                'reason': reason,
                'pnl': current_pnl,
                'levels': basket.current_level,
                'magic': GOLD_HEDGE_MAGIC_BASE,
            }
        
        # Check if new hedge level is needed
        last_level = basket.levels[-1]
        distance_pips = abs(price - last_level.entry_price) / atr if atr > 0 else 0
        
        # Add hedge if price moved against us by hedge_distance_atr * ATR
        if distance_pips >= self.hedge_distance_atr:
            # Determine hedge direction (opposite of last)
            hedge_direction = 'SELL' if last_level.direction == 'BUY' else 'BUY'
            
            return {
                'action': 'ADD_HEDGE',
                'direction': hedge_direction,
                'price': price,
                'atr': atr,
                'level': basket.current_level + 1,
                'reason': f'GOLD_HEDGE: Hedge L{basket.current_level + 1} '
                          f'(dist={distance_pips:.1f}x ATR, PnL=${current_pnl:.2f})',
                'magic': GOLD_HEDGE_MAGIC_BASE,
            }
        
        return None
    
    def execute_signal(self, signal: Dict) -> bool:
        """Execute a signal from analyze().
        
        Args:
            signal: Dict returned by analyze()
            
        Returns:
            True if execution succeeded
        """
        if self.mt5 is None:
            log.warning("GOLD_HEDGE: No MT5Connector — cannot execute")
            return False
        
        action = signal.get('action')
        symbol = signal.get('symbol', 'XAUUSD')
        
        if action == 'OPEN_BASKET':
            return self._execute_open_basket(signal, symbol)
        elif action == 'ADD_HEDGE':
            return self._execute_add_hedge(signal, symbol)
        elif action == 'CLOSE_BASKET':
            return self._execute_close_basket(signal, symbol)
        
        return False
    
    def _execute_open_basket(self, signal: Dict, symbol: str) -> bool:
        """Execute initial basket entry."""
        from execution.broker import BrokerOrder, OrderSide, OrderType
        from decimal import Decimal
        
        direction = signal['direction']
        lots = signal['lots']
        price = signal['price']
        magic = signal['magic']
        
        order = BrokerOrder(
            symbol=symbol,
            side=OrderSide.BUY if direction == 'BUY' else OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal(str(lots)),
            magic_number=magic,
            comment='gold_hedge_init',
        )
        
        try:
            fill = self.mt5.place_order(order)
            
            # Create basket
            basket = self.basket_manager.create_basket(
                symbol=symbol,
                direction=direction,
                entry_price=float(fill.price),
                ticket=int(fill.broker_order_id),
            )
            
            log.info(f"GOLD_HEDGE: Basket opened {symbol} {direction} {lots} lots "
                     f"@ {fill.price} (ticket={fill.broker_order_id})")
            return True
        except Exception as e:
            log.error(f"GOLD_HEDGE: Failed to open basket: {e}")
            return False
    
    def _execute_add_hedge(self, signal: Dict, symbol: str) -> bool:
        """Execute hedge level addition."""
        from execution.broker import BrokerOrder, OrderSide, OrderType
        from decimal import Decimal
        
        direction = signal['direction']
        price = signal['price']
        level = signal['level']
        magic = signal['magic']
        
        # Get lot size from progression
        progression = self.config.get('lot_progression', [0.01, 0.02, 0.03, 0.05, 0.08])
        idx = level - 1
        lots = progression[idx] if idx < len(progression) else progression[-1] * 1.5
        
        order = BrokerOrder(
            symbol=symbol,
            side=OrderSide.BUY if direction == 'BUY' else OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=Decimal(str(lots)),
            magic_number=magic,
            comment=f'gold_hedge_L{level}',
        )
        
        try:
            fill = self.mt5.place_order(order)
            
            # Add to basket
            hedge = self.basket_manager.add_hedge(
                symbol=symbol,
                entry_price=float(fill.price),
                ticket=int(fill.broker_order_id),
            )
            
            if hedge:
                log.info(f"GOLD_HEDGE: Hedge L{level} added {symbol} {direction} {lots} lots "
                         f"@ {fill.price} (ticket={fill.broker_order_id})")
                return True
            return False
        except Exception as e:
            log.error(f"GOLD_HEDGE: Failed to add hedge L{level}: {e}")
            return False
    
    def _execute_close_basket(self, signal: Dict, symbol: str) -> bool:
        """Execute basket close."""
        from execution.broker import OrderSide
        from decimal import Decimal
        
        basket = self.basket_manager.get_basket(symbol)
        if basket is None:
            return False
        
        closed = False
        for level in basket.levels:
            try:
                fill = self.mt5.close_position(level.ticket)
                log.info(f"GOLD_HEDGE: Closed L{level.level} ticket={level.ticket} "
                         f"@ {fill.price}")
                closed = True
            except Exception as e:
                log.error(f"GOLD_HEDGE: Failed to close L{level.level} ticket={level.ticket}: {e}")
        
        if closed:
            self.basket_manager.close_basket(symbol)
            log.info(f"GOLD_HEDGE: Basket fully closed {symbol} — {signal.get('reason')}")
        
        return closed
    
    def get_status(self, symbol: str = 'XAUUSD') -> Dict:
        """Get current status for dashboard display."""
        basket = self.basket_manager.get_basket(symbol)
        if basket is None:
            return {
                'active': False,
                'symbol': symbol,
                'levels': 0,
                'total_lots': 0,
                'pnl': 0,
            }
        
        return {
            'active': True,
            'symbol': symbol,
            'levels': basket.current_level,
            'max_levels': self.config.get('max_hedge_levels', 5),
            'total_lots': basket.total_lots,
            'directions': basket.directions,
            'peak_profit': basket.peak_profit,
            'is_frozen': basket.is_frozen,
            'created_at': basket.created_at.isoformat(),
            'config': {
                'basket_tp_usd': self.config.get('basket_tp_usd', 50.0),
                'freeze_loss_usd': self.config.get('freeze_loss_usd', 200.0),
                'trailing_tp_enabled': self.config.get('trailing_tp_enabled', True),
            }
        }
    
    @staticmethod
    def _calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI."""
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    @staticmethod
    def _calculate_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range."""
        high = data['high']
        low = data['low']
        close = data['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.ewm(span=period, adjust=False).mean()


class GoldHedgeIntegration:
    """Integration bridge between Gold Hedge EA and UnifiedEngine.
    
    UnifiedEngine runs a manual polling loop for non-ScalpingStrategy modules.
    This class provides the integration points.
    """
    
    def __init__(self, config: Dict, mt5_connector):
        """Initialize integration.
        
        Args:
            config: Gold Hedge EA configuration
            mt5_connector: MT5Connector instance
        """
        self.ea = GoldHedgeEA(config, mt5_connector)
        self.mt5 = mt5_connector
        self.enabled = config.get('enabled', False)
    
    def tick(self, symbol: str = 'XAUUSD', data: pd.DataFrame = None):
        """Called by UnifiedEngine's manual loop.
        
        Args:
            symbol: Symbol to check
            data: OHLCV data for the symbol
        """
        if not self.enabled:
            return
        
        signal = self.ea.analyze(symbol, data)
        if signal is not None:
            signal['symbol'] = symbol
            self.ea.execute_signal(signal)
    
    def get_status(self, symbol: str = 'XAUUSD') -> Dict:
        """Get status for API/dashboard."""
        return self.ea.get_status(symbol)
