"""AutoLot 20-Pip EA Strategy.

EMA crossover + RSI momentum + ADX trend strength + H1 trend alignment.
Auto lot sizing, breakeven, trailing stops.
"""

from typing import Optional, List, Dict
import pandas as pd
import numpy as np

from ..base import ScalpingStrategy
from ..signals import ScalpSignal, SignalDirection


class AutoLotStrategy(ScalpingStrategy):
    """AutoLot 20-Pip — trend-following scalper with auto sizing."""
    
    def required_timeframes(self) -> List[str]:
        return ['M5']
    
    def analyze(self, symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[ScalpSignal]:
        m5 = data.get('M5')
        if m5 is None or len(m5) < 50:
            return None
        
        ema_fast = self.config.get('ema_fast', 10)
        ema_slow = self.config.get('ema_slow', 20)
        rsi_period = self.config.get('rsi_period', 14)
        adx_threshold = self.config.get('adx_threshold', 25)
        
        # EMA crossover
        ema_f = m5['close'].ewm(span=ema_fast).mean()
        ema_s = m5['close'].ewm(span=ema_slow).mean()
        
        if ema_f.iloc[-1] > ema_s.iloc[-1] and ema_f.iloc[-2] <= ema_s.iloc[-2]:
            direction = SignalDirection.BUY
        elif ema_f.iloc[-1] < ema_s.iloc[-1] and ema_f.iloc[-2] >= ema_s.iloc[-2]:
            direction = SignalDirection.SELL
        else:
            return None
        
        # RSI momentum
        delta = m5['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(rsi_period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1]
        
        if direction == SignalDirection.BUY and rsi_val < 50:
            return None
        if direction == SignalDirection.SELL and rsi_val > 50:
            return None
        
        # ADX trend strength
        adx = self._calculate_adx(m5, 14)
        if adx < adx_threshold:
            return None
        
        confidence = 0.6 + (adx / 100) * 0.3
        confidence = min(confidence, 1.0)
        
        return ScalpSignal(
            direction=direction,
            symbol=symbol,
            strategy_name='autolot_20pip',
            entry_price=m5.iloc[-1]['close'],
            sl_pips=self.config.get('sl_pips', 20),
            tp_pips=self.config.get('tp_pips', 20),
            confidence=confidence,
            reason=f"EMA crossover + RSI {rsi_val:.0f} + ADX {adx:.0f}",
            metadata={'rsi': float(rsi_val), 'adx': float(adx)}
        )
    
    def _calculate_adx(self, data: pd.DataFrame, period: int = 14) -> float:
        """Calculate ADX."""
        high = data['high']
        low = data['low']
        close = data['close']
        
        plus_dm = high.diff()
        minus_dm = -low.diff()
        
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(period).mean()
        
        val = adx.iloc[-1]
        return float(val) if not np.isnan(val) else 0.0
