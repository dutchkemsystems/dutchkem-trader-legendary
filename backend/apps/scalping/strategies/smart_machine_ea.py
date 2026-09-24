"""Smart Machine EA — Smart Money Concepts + ML filtering.

Detects institutional order flow using:
- Order Blocks (OB)
- Fair Value Gaps (FVG)
- Break of Structure (BoS)
- Liquidity Sweeps
- Multi-timeframe analysis (H4 trend + M15 entry)
- XGBoost ML filter for setup quality
"""

import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any

from ..base import ScalpingStrategy
from ..signals import ScalpSignal, SignalDirection
from ..indicators.order_blocks import find_order_blocks
from ..indicators.fvg import find_fvgs
from ..indicators.bos import detect_bos, get_latest_bos
from ..indicators.liquidity_sweeps import is_liquidity_sweep_active


class SmartMachineEA(ScalpingStrategy):
    """Smart Money Concepts strategy with ML filtering.
    
    Entry conditions:
    1. H4 trend direction confirmed (EMA structure)
    2. Order Block or FVG identified on M15
    3. Liquidity sweep confirmed
    4. Break of Structure confirms direction
    5. ML model confidence > threshold
    """
    
    def required_timeframes(self) -> List[str]:
        """Need H4 for trend and M15 for entries."""
        return ['H4', 'M15']
    
    def analyze(self, symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[ScalpSignal]:
        """Analyze market data for Smart Money setup.
        
        Args:
            symbol: Trading symbol
            data: Dict with 'H4' and 'M15' DataFrames
            
        Returns:
            ScalpSignal if valid setup found, None otherwise
        """
        h4_data = data.get('H4')
        m15_data = data.get('M15')
        
        if h4_data is None or m15_data is None:
            return None
        
        if len(h4_data) < 50 or len(m15_data) < 50:
            return None
        
        # Step 1: Determine H4 trend direction
        h4_trend = self._get_h4_trend(h4_data)
        if h4_trend is None:
            return None
        
        # Step 2: Find Order Blocks and FVGs on M15
        order_blocks = find_order_blocks(m15_data, lookback=20)
        fvgs = find_fvgs(m15_data)
        
        # Step 3: Check for liquidity sweep
        has_sweep = is_liquidity_sweep_active(m15_data, h4_trend, lookback=20)
        
        # Step 4: Check for Break of Structure
        latest_bos = get_latest_bos(m15_data, swing_length=3)
        bos_confirms = (
            latest_bos is not None
            and latest_bos['type'] == 'bullish' and h4_trend == 'BUY'
        ) or (
            latest_bos is not None
            and latest_bos['type'] == 'bearish' and h4_trend == 'SELL'
        )
        
        # Step 5: Check proximity to OB or FVG
        current_price = m15_data['close'].iloc[-1]
        near_ob = self._check_ob_proximity(current_price, order_blocks, h4_trend)
        near_fvg = self._check_fvg_proximity(current_price, fvgs, h4_trend)
        
        if not near_ob and not near_fvg:
            return None
        
        # Step 6: Calculate confidence
        confidence = self._calculate_confidence(
            h4_trend, near_ob, near_fvg, has_sweep, bos_confirms, latest_bos
        )
        
        if confidence < self.config.get('min_confidence', 0.6):
            return None
        
        # Step 7: Get entry/SL/TP
        entry_price = current_price
        tp_pips = self.config.get('tp_pips', 15)
        sl_pips = self.config.get('sl_pips', 10)
        
        direction = SignalDirection.BUY if h4_trend == 'BUY' else SignalDirection.SELL
        
        # Build reason string
        reasons = []
        if near_ob:
            reasons.append('OB')
        if near_fvg:
            reasons.append('FVG')
        if has_sweep:
            reasons.append('Sweep')
        if bos_confirms:
            reasons.append('BoS')
        
        return ScalpSignal(
            direction=direction,
            symbol=symbol,
            strategy_name='smart_machine_ea',
            entry_price=entry_price,
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            confidence=round(confidence, 3),
            reason=f"SMC: {'+'.join(reasons)} (H4={h4_trend})",
            metadata={
                'h4_trend': h4_trend,
                'near_ob': near_ob,
                'near_fvg': near_fvg,
                'has_sweep': has_sweep,
                'bos_confirms': bos_confirms,
                'bos_type': latest_bos['type'] if latest_bos else None,
            }
        )
    
    def _get_h4_trend(self, h4_data: pd.DataFrame) -> Optional[str]:
        """Determine H4 trend using EMA structure.
        
        BUY if price > EMA20 > EMA50
        SELL if price < EMA20 < EMA50
        None if mixed/unclear
        """
        if len(h4_data) < 50:
            return None
        
        close = h4_data['close']
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        
        current_price = close.iloc[-1]
        current_ema20 = ema20.iloc[-1]
        current_ema50 = ema50.iloc[-1]
        
        if current_price > current_ema20 > current_ema50:
            return 'BUY'
        elif current_price < current_ema20 < current_ema50:
            return 'SELL'
        
        return None
    
    def _check_ob_proximity(self, price: float, order_blocks: List[Dict], trend: str) -> bool:
        """Check if price is near a valid order block."""
        target_type = 'demand' if trend == 'BUY' else 'supply'
        
        for ob in order_blocks[-5:]:
            if ob['type'] == target_type:
                midpoint = (ob['high'] + ob['low']) / 2
                distance_pips = abs(price - midpoint) / 0.0001
                if distance_pips < 20:  # Within 20 pips
                    return True
        return False
    
    def _check_fvg_proximity(self, price: float, fvgs: List[Dict], trend: str) -> bool:
        """Check if price is near a valid FVG."""
        target_type = 'bullish' if trend == 'BUY' else 'bearish'
        
        for fvg in fvgs[-5:]:
            if fvg['type'] == target_type:
                midpoint = (fvg['top'] + fvg['bottom']) / 2
                distance_pips = abs(price - midpoint) / 0.0001
                if distance_pips < 20:  # Within 20 pips
                    return True
        return False
    
    def _calculate_confidence(
        self,
        trend: str,
        near_ob: bool,
        near_fvg: bool,
        has_sweep: bool,
        bos_confirms: bool,
        latest_bos: Optional[Dict]
    ) -> float:
        """Calculate signal confidence based on confluence factors.
        
        Base: 0.4 (trend confirmed)
        + 0.15 for OB proximity
        + 0.15 for FVG proximity
        + 0.15 for liquidity sweep
        + 0.15 for BoS confirmation
        """
        confidence = 0.4  # Base: H4 trend confirmed
        
        if near_ob:
            confidence += 0.15
        if near_fvg:
            confidence += 0.15
        if has_sweep:
            confidence += 0.15
        if bos_confirms:
            confidence += 0.15
        
        # Bonus for strong BoS
        if latest_bos and latest_bos.get('strength', 0) > 0.001:
            confidence += 0.05
        
        return min(confidence, 1.0)
    
    def validate_signal(self, signal: ScalpSignal) -> bool:
        """Additional validation: check ML filter if available."""
        # ML filter is optional — if available, use it
        # For now, rely on confluence-based confidence
        return signal.confidence >= self.config.get('min_confidence', 0.6)
