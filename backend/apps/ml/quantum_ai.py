"""Quantum AI Module — 12-Weight Adaptive Scoring System.

Inspired by Ultimate AI v24.004 from MT4. Implements 12 weighted factors
that combine technical, volume, pattern, seasonal, and quantum analysis
into a single adaptive score.

Each factor produces a score (-1 to 1) and has a weight (0 to 1).
The final score is the weighted sum, normalized to [-1, 1].

Weights adapt based on recent win rate per factor.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Default 12 weights (from Ultimate AI v24.004)
DEFAULT_WEIGHTS = {
    'trend': 0.15,        # Layer 1: Technical Analysis
    'momentum': 0.10,     # Layer 1: Technical Analysis
    'volatility': 0.08,   # Layer 1: Technical Analysis
    'volume': 0.12,       # Layer 2: Volume Analysis
    'sr': 0.10,           # Layer 1: Technical Analysis
    'pattern': 0.08,      # Layer 5: Quantum Pattern Recognition
    'time': 0.07,         # Layer 4: Seasonal Patterns
    'gold': 0.05,         # Gold-specific factor
    'quantum': 0.10,      # Layer 5: Quantum Pattern Recognition
    'neural': 0.05,       # Layer 6: Neural Network
    'seasonal': 0.05,     # Layer 4: Seasonal Patterns
    'market_memory': 0.05, # Layer 3: Market Memory
}

# Weight bounds (prevent any single factor from dominating)
WEIGHT_MIN = 0.02
WEIGHT_MAX = 0.30
WEIGHT_LEARNING_RATE = 0.05  # How fast weights adapt


@dataclass
class QuantumScore:
    """Result of Quantum AI scoring."""
    score: float  # -1 to 1
    direction: str  # BUY/SELL/HOLD
    confidence: float  # 0 to 1
    factor_scores: Dict[str, float]
    weights: Dict[str, float]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class QuantumAI:
    """12-weight adaptive scoring system.
    
    Usage:
        ai = QuantumAI()
        score = ai.score(candles, features)
        if score.direction == 'BUY' and score.confidence > 0.6:
            # Execute buy
    """
    
    def __init__(self, weights: Optional[Dict[str, float]] = None, persistence_path: str = None):
        """Initialize Quantum AI.
        
        Args:
            weights: Custom weights (dict of factor_name -> weight).
                     If None, uses DEFAULT_WEIGHTS.
            persistence_path: Path to save/load weight adaptations.
        """
        self.weights = dict(weights or DEFAULT_WEIGHTS)
        self.persistence_path = persistence_path
        self._normalize_weights()
        
        # Win rate tracking per factor (for adaptive weights)
        self._factor_wins: Dict[str, int] = {k: 0 for k in self.weights}
        self._factor_attempts: Dict[str, int] = {k: 0 for k in self.weights}
        
        # Load persisted state
        if persistence_path and os.path.exists(persistence_path):
            self._load_state()
    
    def score(self, candles: pd.DataFrame, features: Optional[Dict] = None) -> QuantumScore:
        """Calculate quantum AI score from market data.
        
        Args:
            candles: OHLCV DataFrame (at least 50 bars)
            features: Pre-computed feature dict (optional)
            
        Returns:
            QuantumScore with direction, confidence, and factor breakdown
        """
        if candles is None or len(candles) < 30:
            return QuantumScore(score=0, direction='HOLD', confidence=0,
                                factor_scores={}, weights=dict(self.weights))
        
        # Calculate all 12 factor scores
        factor_scores = {}
        factor_scores['trend'] = self._score_trend(candles)
        factor_scores['momentum'] = self._score_momentum(candles)
        factor_scores['volatility'] = self._score_volatility(candles)
        factor_scores['volume'] = self._score_volume(candles)
        factor_scores['sr'] = self._score_support_resistance(candles)
        factor_scores['pattern'] = self._score_pattern(candles)
        factor_scores['time'] = self._score_time(candles)
        factor_scores['gold'] = self._score_gold(candles, features)
        factor_scores['quantum'] = self._score_quantum(candles)
        factor_scores['neural'] = self._score_neural(candles)
        factor_scores['seasonal'] = self._score_seasonal(candles)
        factor_scores['market_memory'] = self._score_market_memory(candles)
        
        # Calculate weighted score
        weighted_sum = sum(
            factor_scores[k] * self.weights[k]
            for k in self.weights if k in factor_scores
        )
        
        # Normalize to [-1, 1]
        total_weight = sum(self.weights[k] for k in self.weights if k in factor_scores)
        if total_weight > 0:
            final_score = weighted_sum / total_weight
        else:
            final_score = 0
        
        final_score = np.clip(final_score, -1.0, 1.0)
        
        # Direction
        if final_score > 0.15:
            direction = 'BUY'
        elif final_score < -0.15:
            direction = 'SELL'
        else:
            direction = 'HOLD'
        
        # Confidence is absolute score magnitude
        confidence = min(abs(final_score) * 1.5, 1.0)
        
        return QuantumScore(
            score=final_score,
            direction=direction,
            confidence=confidence,
            factor_scores=factor_scores,
            weights=dict(self.weights),
        )
    
    def adapt_weights(self, factor_name: str, was_win: bool):
        """Adapt weights based on trade outcome.
        
        Args:
            factor_name: Which factor contributed to the trade
            was_win: Whether the trade was profitable
        """
        if factor_name not in self.weights:
            return
        
        self._factor_attempts[factor_name] = self._factor_attempts.get(factor_name, 0) + 1
        if was_win:
            self._factor_wins[factor_name] = self._factor_wins.get(factor_name, 0) + 1
        
        # Calculate win rate for this factor
        attempts = self._factor_attempts[factor_name]
        if attempts < 5:
            return  # Need at least 5 samples
        
        win_rate = self._factor_wins[factor_name] / attempts
        
        # Adjust weight: increase if win rate > 50%, decrease otherwise
        delta = (win_rate - 0.5) * WEIGHT_LEARNING_RATE
        self.weights[factor_name] = np.clip(
            self.weights[factor_name] + delta,
            WEIGHT_MIN,
            WEIGHT_MAX
        )
        
        self._normalize_weights()
        
        # Persist
        if self.persistence_path:
            self._save_state()
    
    def _normalize_weights(self):
        """Normalize weights to sum to 1.0."""
        total = sum(self.weights.values())
        if total > 0:
            for k in self.weights:
                self.weights[k] /= total
    
    # ─── Factor Scoring Methods ──────────────────────────────────────
    
    def _score_trend(self, candles: pd.DataFrame) -> float:
        """Trend alignment score using EMAs."""
        close = candles['close']
        ema9 = close.ewm(span=9, adjust=False).mean()
        ema21 = close.ewm(span=21, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean() if len(close) >= 50 else ema21
        
        price = close.iloc[-1]
        e9, e21, e50 = ema9.iloc[-1], ema21.iloc[-1], ema50.iloc[-1]
        
        if price > e9 > e21 > e50:
            return 1.0  # Strong bullish
        elif price > e21 > e50:
            return 0.6  # Moderate bullish
        elif price < e9 < e21 < e50:
            return -1.0  # Strong bearish
        elif price < e21 < e50:
            return -0.6  # Moderate bearish
        return 0.0
    
    def _score_momentum(self, candles: pd.DataFrame) -> float:
        """Momentum score using RSI + MACD."""
        close = candles['close']
        
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=13, min_periods=14).mean()
        avg_loss = loss.ewm(com=13, min_periods=14).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(span=9, adjust=False).mean()
        macd_hist = macd - signal_line
        
        # Combine RSI and MACD
        rsi_score = (current_rsi - 50) / 50  # -1 to 1
        macd_score = np.clip(macd_hist.iloc[-1] / (abs(close.iloc[-1]) * 0.01 + 1e-10), -1, 1)
        
        return (rsi_score + macd_score) / 2
    
    def _score_volatility(self, candles: pd.DataFrame) -> float:
        """Volatility score using Bollinger Bands + ATR."""
        close = candles['close']
        high = candles['high']
        low = candles['low']
        
        # Bollinger Bands
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_upper = sma20 + 2 * std20
        bb_lower = sma20 - 2 * std20
        bb_width = (bb_upper - bb_lower) / (sma20 + 1e-10)
        
        # ATR
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(span=14, adjust=False).mean()
        atr_pct = atr / (close + 1e-10)
        
        current_bb_width = bb_width.iloc[-1] if not bb_width.empty else 0
        current_atr_pct = atr_pct.iloc[-1] if not atr_pct.empty else 0
        
        # Low volatility = squeeze = potential breakout
        if current_bb_width < 0.02:
            return 0.3  # Squeeze — slight bullish bias (expect expansion)
        elif current_bb_width > 0.06:
            return -0.3  # High volatility — caution
        return 0.0
    
    def _score_volume(self, candles: pd.DataFrame) -> float:
        """Volume analysis score."""
        if 'volume' not in candles.columns:
            return 0.0
        
        volume = candles['volume']
        vol_sma = volume.rolling(20).mean()
        
        current_vol = volume.iloc[-1]
        avg_vol = vol_sma.iloc[-1] if not vol_sma.empty else current_vol
        
        if avg_vol == 0:
            return 0.0
        
        vol_ratio = current_vol / avg_vol
        
        # High volume + price up = bullish, price down = bearish
        price_change = candles['close'].iloc[-1] - candles['close'].iloc[-2] if len(candles) > 1 else 0
        
        if vol_ratio > 1.5:
            return 0.8 if price_change > 0 else -0.8
        elif vol_ratio > 1.2:
            return 0.4 if price_change > 0 else -0.4
        return 0.0
    
    def _score_support_resistance(self, candles: pd.DataFrame) -> float:
        """S/R proximity score."""
        close = candles['close']
        current = close.iloc[-1]
        
        # Dynamic S/R from 20-period highs/lows
        highs = candles['high'].rolling(20).max()
        lows = candles['low'].rolling(20).min()
        
        resistance = highs.iloc[-1] if not highs.empty else current
        support = lows.iloc[-1] if not lows.empty else current
        
        range_size = resistance - support
        if range_size == 0:
            return 0.0
        
        # Position within range: 0 = at support, 1 = at resistance
        position = (current - support) / range_size
        
        # Near support = bullish potential, near resistance = bearish potential
        if position < 0.2:
            return 0.6  # Near support
        elif position > 0.8:
            return -0.6  # Near resistance
        return 0.0
    
    def _score_pattern(self, candles: pd.DataFrame) -> float:
        """Candlestick pattern score."""
        if len(candles) < 3:
            return 0.0
        
        # Check last 3 candles for patterns
        o = candles['open'].iloc[-3:]
        h = candles['high'].iloc[-3:]
        l = candles['low'].iloc[-3:]
        c = candles['close'].iloc[-3:]
        
        score = 0.0
        
        # Bullish engulfing
        if (c.iloc[-2] < o.iloc[-2] and  # Previous bearish
            c.iloc[-1] > o.iloc[-1] and   # Current bullish
            c.iloc[-1] > o.iloc[-2] and   # Current close > previous open
            o.iloc[-1] < c.iloc[-2]):     # Current open < previous close
            score += 0.5
        
        # Bearish engulfing
        if (c.iloc[-2] > o.iloc[-2] and
            c.iloc[-1] < o.iloc[-1] and
            c.iloc[-1] < o.iloc[-2] and
            o.iloc[-1] > c.iloc[-2]):
            score -= 0.5
        
        # Hammer (bullish)
        body = abs(c.iloc[-1] - o.iloc[-1])
        lower_shadow = min(o.iloc[-1], c.iloc[-1]) - l.iloc[-1]
        upper_shadow = h.iloc[-1] - max(o.iloc[-1], c.iloc[-1])
        if lower_shadow > 2 * body and upper_shadow < body:
            score += 0.3
        
        # Shooting star (bearish)
        if upper_shadow > 2 * body and lower_shadow < body:
            score -= 0.3
        
        return np.clip(score, -1.0, 1.0)
    
    def _score_time(self, candles: pd.DataFrame) -> float:
        """Time-based score (session awareness)."""
        now = datetime.now(timezone.utc)
        hour = now.hour
        
        # London session: 07:00-16:00 UTC
        if 7 <= hour <= 16:
            return 0.2
        # NY session: 12:00-21:00 UTC
        elif 12 <= hour <= 21:
            return 0.3  # NY session slightly stronger
        # Asian session: low activity
        elif 0 <= hour <= 6:
            return -0.1
        # Late NY / early Asian
        else:
            return 0.0
    
    def _score_gold(self, candles: pd.DataFrame, features: Optional[Dict] = None) -> float:
        """Gold-specific scoring (for XAUUSD)."""
        if features is None:
            features = {}
        
        # If not gold, return neutral
        if features.get('symbol', '').upper() not in ('XAUUSD', 'XAU'):
            return 0.0
        
        # Gold-specific: higher ATR = opportunity
        close = candles['close']
        high = candles['high']
        low = candles['low']
        
        tr = high - low
        atr = tr.ewm(span=14, adjust=False).mean()
        atr_pct = atr / (close + 1e-10)
        
        current_atr_pct = atr_pct.iloc[-1] if not atr_pct.empty else 0
        
        if current_atr_pct > 0.005:
            return 0.4  # High gold volatility = opportunity
        elif current_atr_pct < 0.001:
            return -0.2  # Low gold volatility = caution
        return 0.0
    
    def _score_quantum(self, candles: pd.DataFrame) -> float:
        """Quantum pattern recognition score (fractal-like analysis)."""
        if len(candles) < 20:
            return 0.0
        
        close = candles['close'].values
        
        # Calculate fractal dimension approximation
        # Using box-counting method (simplified)
        n = min(20, len(close))
        prices = close[-n:]
        
        # Price range
        price_range = max(prices) - min(prices)
        if price_range == 0:
            return 0.0
        
        # Count direction changes
        changes = np.diff(prices)
        sign_changes = np.sum(np.abs(np.diff(np.sign(changes)))) / 2
        
        # Normalize: more changes = more complex = higher score
        complexity = sign_changes / (n - 2)
        
        # Recent momentum
        recent_change = (prices[-1] - prices[0]) / (prices[0] + 1e-10)
        
        return np.clip(recent_change * 10 + complexity * 0.5, -1.0, 1.0)
    
    def _score_neural(self, candles: pd.DataFrame) -> float:
        """Simple neural-like scoring (feedforward approximation)."""
        close = candles['close']
        
        # 5 inputs (like GrokUltimateForexPro perceptron)
        rsi = self._quick_rsi(close)
        ma_diff = (close.iloc[-1] - close.rolling(20).mean().iloc[-1]) / (close.iloc[-1] + 1e-10)
        
        if 'volume' in candles.columns:
            vol_ratio = candles['volume'].iloc[-1] / (candles['volume'].rolling(20).mean().iloc[-1] + 1e-10)
        else:
            vol_ratio = 1.0
        
        momentum = (close.iloc[-1] - close.iloc[-5]) / (close.iloc[-5] + 1e-10) if len(close) >= 5 else 0
        
        # Simple weighted combination (simulates perceptron)
        inputs = np.array([
            (rsi - 50) / 50,      # Normalized RSI
            np.clip(ma_diff * 10, -1, 1),  # MA difference
            np.clip(vol_ratio - 1, -1, 1),  # Volume ratio
            np.clip(momentum * 10, -1, 1),  # Momentum
            0.0  # S/R placeholder
        ])
        
        # Fixed weights (simulating trained perceptron)
        w = np.array([0.2, 0.3, 0.2, 0.15, 0.15])
        output = np.tanh(np.dot(inputs, w))
        
        return float(output)
    
    def _score_seasonal(self, candles: pd.DataFrame) -> float:
        """Seasonal/time-of-day scoring."""
        now = datetime.now(timezone.utc)
        
        # Day of week patterns
        day = now.weekday()  # 0=Monday
        hour = now.hour
        
        # Monday open: often gaps
        if day == 0 and 7 <= hour <= 10:
            return 0.3
        
        # Friday close: reduce positions
        if day == 4 and hour >= 18:
            return -0.4
        
        # Wednesday: mid-week reversal day
        if day == 2:
            return 0.1
        
        return 0.0
    
    def _score_market_memory(self, candles: pd.DataFrame) -> float:
        """Market memory score (pattern similarity)."""
        if len(candles) < 20:
            return 0.0
        
        close = candles['close'].values
        
        # Compare last 5 bars to previous 5-bar patterns
        recent = close[-5:]
        patterns = []
        
        for i in range(len(close) - 10, len(close) - 5):
            if i >= 0:
                pattern = close[i:i+5]
                # Normalize pattern
                pattern = (pattern - pattern[0]) / (pattern[0] + 1e-10)
                patterns.append(pattern)
        
        if not patterns:
            return 0.0
        
        # Normalize recent pattern
        recent_norm = (recent - recent[0]) / (recent[0] + 1e-10)
        
        # Find best match
        best_sim = 0
        for pat in patterns:
            sim = 1.0 - np.mean(np.abs(pat - recent_norm))
            best_sim = max(best_sim, sim)
        
        # High similarity = expect similar outcome
        return np.clip(best_sim * 2 - 1, -1.0, 1.0)
    
    def _quick_rsi(self, close: pd.Series, period: int = 14) -> float:
        """Quick RSI calculation for last value only."""
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not rsi.empty else 50.0
    
    # ─── Persistence ──────────────────────────────────────────────────
    
    def _save_state(self):
        """Save weights and win rates to disk."""
        state = {
            'weights': self.weights,
            'factor_wins': self._factor_wins,
            'factor_attempts': self._factor_attempts,
            'saved_at': datetime.now(timezone.utc).isoformat(),
        }
        os.makedirs(os.path.dirname(self.persistence_path), exist_ok=True)
        with open(self.persistence_path, 'w') as f:
            json.dump(state, f, indent=2)
    
    def _load_state(self):
        """Load weights and win rates from disk."""
        try:
            with open(self.persistence_path, 'r') as f:
                state = json.load(f)
            self.weights = state.get('weights', DEFAULT_WEIGHTS)
            self._factor_wins = state.get('factor_wins', {k: 0 for k in self.weights})
            self._factor_attempts = state.get('factor_attempts', {k: 0 for k in self.weights})
            log.info(f"QuantumAI: Loaded weights from {self.persistence_path}")
        except Exception as e:
            log.warning(f"QuantumAI: Failed to load state: {e}")
