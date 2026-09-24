"""Volume Spread Analysis (VSA) — Supply/Demand Detection.

Inspired by GrokUltimateForexPro from MT4. Analyzes the relationship
between spread (high-low range), close position within spread, and volume
to determine institutional supply/demand.

Key VSA concepts:
- No Demand: Narrow spread, low volume, up-close (at top) — bearish
- No Supply: Narrow spread, low volume, down-close (at bottom) — bullish
- Stopping Volume: High volume, narrow spread, at extreme — reversal
- Test: High volume, narrow spread, tests previous level — reversal
- Accumulation: High volume, wide spread, up-close — bullish
- Distribution: High volume, wide spread, down-close — bearish
- Climax: Very high volume, wide spread, at extreme — reversal
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


class VSAPattern(Enum):
    """VSA pattern types."""
    NO_DEMAND = 'no_demand'           # Bearish: narrow, low vol, up-close
    NO_SUPPLY = 'no_supply'           # Bullish: narrow, low vol, down-close
    STOPPING_VOLUME = 'stopping_volume'  # Reversal: high vol, narrow, at extreme
    TEST = 'test'                     # Reversal: high vol, narrow, tests level
    ACCUMULATION = 'accumulation'     # Bullish: high vol, wide, up-close
    DISTRIBUTION = 'distribution'     # Bearish: high vol, wide, down-close
    CLIMAX_UP = 'climax_up'           # Reversal: very high vol, wide, top
    CLIMAX_DOWN = 'climax_down'       # Reversal: very high vol, wide, bottom
    NEUTRAL = 'neutral'               # No clear signal


@dataclass
class VSASignal:
    """A VSA signal from candle analysis."""
    pattern: VSAPattern
    direction: str  # 'BUY', 'SELL', 'NEUTRAL'
    strength: float  # 0-1
    candle_index: int
    details: Dict


class VSADetector:
    """Volume Spread Analysis detector.
    
    Usage:
        detector = VSADetector()
        signals = detector.analyze(candles)
        
        # Check for entry confirmation
        if detector.confirm_entry(candles, direction='BUY'):
            # VSA confirms buy entry
    """
    
    def __init__(
        self,
        volume_lookback: int = 20,
        spread_lookback: int = 20,
        volume_threshold: float = 1.5,
        narrow_spread_pct: float = 0.5,
        wide_spread_pct: float = 1.5,
    ):
        """Initialize VSA detector.
        
        Args:
            volume_lookback: Bars to calculate average volume
            spread_lookback: Bars to calculate average spread
            volume_threshold: Multiplier for "high volume" detection
            narrow_spread_pct: Percentile for "narrow" spread
            wide_spread_pct: Percentile for "wide" spread
        """
        self.volume_lookback = volume_lookback
        self.spread_lookback = spread_lookback
        self.volume_threshold = volume_threshold
        self.narrow_spread_pct = narrow_spread_pct
        self.wide_spread_pct = wide_spread_pct
    
    def analyze(self, candles: pd.DataFrame) -> List[VSASignal]:
        """Analyze candles for VSA patterns.
        
        Args:
            candles: OHLCV DataFrame (at least 30 bars recommended)
            
        Returns:
            List of VSASignal for each candle with a pattern
        """
        if candles is None or len(candles) < self.volume_lookback + 5:
            return []
        
        signals = []
        
        # Calculate metrics
        spread = candles['high'] - candles['low']
        avg_spread = spread.rolling(self.spread_lookback).mean()
        avg_volume = candles['volume'].rolling(self.volume_lookback).mean() if 'volume' in candles.columns else None
        
        for i in range(self.volume_lookback, len(candles)):
            candle = candles.iloc[i]
            candle_spread = spread.iloc[i]
            candle_volume = candle.get('volume', 0)
            
            if avg_volume is not None and not pd.isna(avg_volume.iloc[i]):
                vol_ratio = candle_volume / (avg_volume.iloc[i] + 1e-10)
            else:
                vol_ratio = 1.0
            
            avg_sp = avg_spread.iloc[i] if not pd.isna(avg_spread.iloc[i]) else candle_spread
            
            # Close position within spread (0 = at low, 1 = at high)
            if candle_spread > 0:
                close_pos = (candle['close'] - candle['low']) / candle_spread
            else:
                close_pos = 0.5
            
            # Detect pattern
            pattern = self._classify_candle(
                candle_spread, avg_sp, vol_ratio, close_pos, candle, candles, i
            )
            
            if pattern != VSAPattern.NEUTRAL:
                direction, strength = self._pattern_to_signal(pattern, close_pos)
                signals.append(VSASignal(
                    pattern=pattern,
                    direction=direction,
                    strength=strength,
                    candle_index=i,
                    details={
                        'spread': candle_spread,
                        'volume_ratio': vol_ratio,
                        'close_position': close_pos,
                        'avg_spread': avg_sp,
                    }
                ))
        
        return signals
    
    def confirm_entry(self, candles: pd.DataFrame, direction: str, lookback: int = 5) -> bool:
        """Check if recent VSA confirms a trade entry.
        
        Args:
            candles: OHLCV DataFrame
            direction: 'BUY' or 'SELL'
            lookback: How many recent bars to check
            
        Returns:
            True if VSA confirms the direction
        """
        signals = self.analyze(candles)
        
        if not signals:
            return False
        
        # Check recent signals
        recent = [s for s in signals if s.candle_index >= len(candles) - lookback]
        
        if not recent:
            return False
        
        # For BUY: look for bullish VSA patterns
        if direction == 'BUY':
            bullish = [s for s in recent if s.direction == 'BUY']
            return len(bullish) >= 1  # At least 1 bullish VSA signal
        
        # For SELL: look for bearish VSA patterns
        elif direction == 'SELL':
            bearish = [s for s in recent if s.direction == 'SELL']
            return len(bearish) >= 1
        
        return False
    
    def get_latest_signal(self, candles: pd.DataFrame) -> Optional[VSASignal]:
        """Get the most recent VSA signal."""
        signals = self.analyze(candles)
        return signals[-1] if signals else None
    
    def _classify_candle(
        self,
        spread: float,
        avg_spread: float,
        vol_ratio: float,
        close_pos: float,
        candle: pd.Series,
        candles: pd.DataFrame,
        index: int,
    ) -> VSAPattern:
        """Classify a single candle into VSA pattern."""
        
        # Determine spread classification
        if avg_spread > 0:
            spread_ratio = spread / avg_spread
        else:
            spread_ratio = 1.0
        
        is_narrow = spread_ratio < self.narrow_spread_pct
        is_wide = spread_ratio > self.wide_spread_pct
        is_normal = not is_narrow and not is_wide
        
        is_high_vol = vol_ratio > self.volume_threshold
        is_low_vol = vol_ratio < 0.7
        is_normal_vol = not is_high_vol and not is_low_vol
        
        # Check if at price extreme
        at_top = close_pos > 0.7
        at_bottom = close_pos < 0.3
        at_middle = not at_top and not at_bottom
        
        # ─── VSA Pattern Classification ──────────────────────────────
        
        # No Demand: narrow spread, low volume, up-close (at top)
        if is_narrow and is_low_vol and at_top:
            return VSAPattern.NO_DEMAND
        
        # No Supply: narrow spread, low volume, down-close (at bottom)
        if is_narrow and is_low_vol and at_bottom:
            return VSAPattern.NO_SUPPLY
        
        # Stopping Volume: high volume, narrow/normal spread, at extreme
        if is_high_vol and (is_narrow or is_normal):
            if at_top or at_bottom:
                return VSAPattern.STOPPING_VOLUME
        
        # Test: high volume, narrow spread, tests previous level
        if is_high_vol and is_narrow:
            # Check if testing a previous support/resistance
            if index >= 5:
                prev_highs = candles['high'].iloc[max(0, index-20):index]
                prev_lows = candles['low'].iloc[max(0, index-20):index]
                current_low = candle['low']
                current_high = candle['high']
                
                # Test of support
                near_support = any(abs(current_low - low) < spread * 0.3 
                                  for low in prev_lows)
                # Test of resistance
                near_resistance = any(abs(current_high - high) < spread * 0.3 
                                     for high in prev_highs)
                
                if near_support or near_resistance:
                    return VSAPattern.TEST
        
        # Climax Up: very high volume (>2x), wide spread, at top
        if vol_ratio > 2.0 and is_wide and at_top:
            return VSAPattern.CLIMAX_UP
        
        # Climax Down: very high volume (>2x), wide spread, at bottom
        if vol_ratio > 2.0 and is_wide and at_bottom:
            return VSAPattern.CLIMAX_DOWN
        
        # Accumulation: high volume, wide spread, up-close
        if is_high_vol and is_wide and at_top:
            return VSAPattern.ACCUMULATION
        
        # Distribution: high volume, wide spread, down-close
        if is_high_vol and is_wide and at_bottom:
            return VSAPattern.DISTRIBUTION
        
        return VSAPattern.NEUTRAL
    
    def _pattern_to_signal(self, pattern: VSAPattern, close_pos: float) -> tuple:
        """Convert VSA pattern to direction and strength."""
        
        BULLISH_PATTERNS = {
            VSAPattern.NO_SUPPLY: 0.5,
            VSAPattern.ACCUMULATION: 0.8,
            VSAPattern.STOPPING_VOLUME: 0.7,
            VSAPattern.TEST: 0.6,
            VSAPattern.CLIMAX_DOWN: 0.9,  # Reversal from bottom
        }
        
        BEARISH_PATTERNS = {
            VSAPattern.NO_DEMAND: 0.5,
            VSAPattern.DISTRIBUTION: 0.8,
            VSAPattern.STOPPING_VOLUME: 0.7,
            VSAPattern.TEST: 0.6,
            VSAPattern.CLIMAX_UP: 0.9,  # Reversal from top
        }
        
        if pattern in BULLISH_PATTERNS:
            return 'BUY', BULLISH_PATTERNS[pattern]
        elif pattern in BEARISH_PATTERNS:
            return 'SELL', BEARISH_PATTERNS[pattern]
        
        return 'NEUTRAL', 0.0
