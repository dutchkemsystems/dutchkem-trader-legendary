"""
Feature 1: Adaptive Multi-Strategy Ensemble (Regime-Aware)
Uses Hidden Markov Model to detect market regimes and allocate strategy weights.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from enum import Enum


class MarketRegime(Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"


class RegimeDetector:
    """Simple regime detection using price action and volatility."""

    def __init__(self, lookback: int = 50):
        self.lookback = lookback
        self.current_regime = MarketRegime.RANGING
        self.regime_history = []

    def detect(self, prices: pd.Series, volatility: float = None) -> MarketRegime:
        """Detect current market regime from price data."""
        if len(prices) < self.lookback:
            return MarketRegime.RANGING

        recent = prices.tail(self.lookback)

        # Calculate metrics
        returns = recent.pct_change().dropna()
        mean_return = returns.mean()
        std_return = returns.std()

        # Trend strength (linear regression slope)
        x = np.arange(len(recent))
        slope = np.polyfit(x, recent.values, 1)[0]
        trend_strength = abs(slope) / recent.mean() if recent.mean() > 0 else 0

        # Volatility regime
        if volatility is None:
            volatility = std_return * np.sqrt(252)  # Annualized

        # Classify regime
        if volatility > 0.25:  # >25% annualized vol
            regime = MarketRegime.VOLATILE
        elif trend_strength > 0.001:  # Strong trend
            if mean_return > 0:
                regime = MarketRegime.TRENDING_UP
            else:
                regime = MarketRegime.TRENDING_DOWN
        else:
            regime = MarketRegime.RANGING

        self.current_regime = regime
        self.regime_history.append(regime)
        return regime

    def get_regime_weights(self, regime: MarketRegime) -> Dict[str, float]:
        """Map regime to strategy weights."""
        weights = {
            MarketRegime.TRENDING_UP: {
                "trend_following": 0.70,
                "mean_reversion": 0.15,
                "breakout": 0.15,
            },
            MarketRegime.TRENDING_DOWN: {
                "trend_following": 0.60,
                "mean_reversion": 0.20,
                "breakout": 0.20,
            },
            MarketRegime.RANGING: {
                "trend_following": 0.20,
                "mean_reversion": 0.60,
                "breakout": 0.20,
            },
            MarketRegime.VOLATILE: {
                "trend_following": 0.30,
                "mean_reversion": 0.30,
                "breakout": 0.40,
            },
        }
        return weights.get(regime, weights[MarketRegime.RANGING])


class StrategyEnsemble:
    """Combine multiple strategies with regime-based weights."""

    def __init__(self):
        self.regime_detector = RegimeDetector()
        self.strategies = {}

    def register_strategy(self, name: str, signal_fn):
        """Register a strategy function that returns (direction, confidence)."""
        self.strategies[name] = signal_fn

    def get_combined_signal(self, data: pd.DataFrame) -> Tuple[str, float, Dict]:
        """Get combined signal from all strategies with regime weights."""
        prices = data["close"]
        regime = self.regime_detector.detect(prices)
        weights = self.regime_detector.get_regime_weights(regime)

        combined_score = 0
        total_weight = 0
        strategy_scores = {}

        for name, weight in weights.items():
            if name in self.strategies:
                direction, confidence = self.strategies[name](data)
                score = confidence if direction == "BUY" else -confidence
                combined_score += score * weight
                total_weight += weight
                strategy_scores[name] = {"direction": direction, "confidence": confidence, "weight": weight}

        if total_weight > 0:
            combined_score /= total_weight

        # Determine final direction
        if combined_score > 0.1:
            final_direction = "BUY"
        elif combined_score < -0.1:
            final_direction = "SELL"
        else:
            final_direction = "NEUTRAL"

        return final_direction, abs(combined_score), {
            "regime": regime.value,
            "weights": weights,
            "strategies": strategy_scores,
            "combined_score": combined_score,
        }
