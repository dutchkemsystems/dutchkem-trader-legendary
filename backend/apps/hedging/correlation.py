"""
Feature 3: Cross-Asset Correlation Hedging
Automatically hedge open positions with correlated assets.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from datetime import datetime, timezone


class CorrelationHedge:
    """Manage correlation-based hedges for open positions."""

    def __init__(self, lookback: int = 50, threshold: float = 0.7):
        self.lookback = lookback
        self.threshold = threshold
        self.hedge_positions = {}
        self.correlation_cache = {}

    def compute_correlations(self, price_data: Dict[str, pd.Series]) -> pd.DataFrame:
        """Compute rolling correlations between all symbols."""
        df = pd.DataFrame(price_data)
        if len(df) < self.lookback:
            return pd.DataFrame()

        returns = df.pct_change().dropna()
        corr_matrix = returns.tail(self.lookback).corr()

        self.correlation_cache = {
            "matrix": corr_matrix,
            "timestamp": datetime.now(timezone.utc),
        }

        return corr_matrix

    def find_correlated_pairs(self, positions: List[str], corr_matrix: pd.DataFrame) -> List[Tuple[str, str, float]]:
        """Find highly correlated position pairs."""
        pairs = []
        for i, sym1 in enumerate(positions):
            for sym2 in positions[i + 1:]:
                if sym1 in corr_matrix.index and sym2 in corr_matrix.columns:
                    corr = abs(corr_matrix.loc[sym1, sym2])
                    if corr >= self.threshold:
                        pairs.append((sym1, sym2, corr))

        return sorted(pairs, key=lambda x: x[2], reverse=True)

    def calculate_hedge_size(self, pos1_size: float, pos2_size: float, corr: float) -> float:
        """Calculate hedge size based on correlation and position sizes."""
        # Hedge = 30-50% of the larger position, scaled by correlation
        max_size = max(pos1_size, pos2_size)
        hedge_pct = 0.3 + (corr - self.threshold) * (0.2 / (1 - self.threshold))
        hedge_pct = min(hedge_pct, 0.5)
        return round(max_size * hedge_pct, 2)

    def should_hedge(self, symbol: str, direction: str, size: float,
                     open_positions: Dict, corr_matrix: pd.DataFrame) -> Dict:
        """Determine if a new hedge is needed."""
        if symbol not in corr_matrix.index:
            return {"hedge": False, "reason": "no_correlation_data"}

        # Check correlations with existing positions
        for other_sym, other_pos in open_positions.items():
            if other_sym == symbol:
                continue
            if other_sym not in corr_matrix.columns:
                continue

            corr = abs(corr_matrix.loc[symbol, other_sym])
            if corr >= self.threshold:
                # Check if positions are in same direction (additive risk)
                if other_pos.get("action") == direction:
                    hedge_size = self.calculate_hedge_size(
                        size, other_pos.get("size", 0), corr
                    )
                    hedge_direction = "SELL" if direction == "BUY" else "BUY"

                    return {
                        "hedge": True,
                        "hedge_symbol": other_sym,
                        "hedge_direction": hedge_direction,
                        "hedge_size": hedge_size,
                        "correlation": corr,
                        "reason": f"high_correlation_{corr:.2f}",
                    }

        return {"hedge": False, "reason": "no_hedge_needed"}

    def get_net_exposure(self, positions: Dict) -> Dict:
        """Calculate net exposure across all positions."""
        exposure = {"long": 0, "short": 0, "net": 0, "heat": 0}

        for sym, pos in positions.items():
            size = pos.get("size", 0)
            if pos.get("action") == "BUY":
                exposure["long"] += size
            else:
                exposure["short"] += size

        exposure["net"] = exposure["long"] - exposure["short"]
        total = exposure["long"] + exposure["short"]
        exposure["heat"] = total / 10 if total > 0 else 0  # Normalize to 0-10 scale

        return exposure
