"""
Feature 7: Dynamic Risk Parity
Allocate risk to each symbol based on volatility and correlation.
"""
import numpy as np
import pandas as pd
from typing import Dict, List
from datetime import datetime, timezone


class RiskParity:
    """Calculate risk parity weights for position sizing."""

    def __init__(self, lookback: int = 50):
        self.lookback = lookback
        self.weights = {}
        self.last_rebalance = None

    def calculate_volatility(self, prices: pd.Series) -> float:
        """Calculate annualized volatility for a symbol."""
        if len(prices) < 10:
            return 0.20  # Default 20%

        returns = prices.pct_change().dropna()
        vol = returns.std() * np.sqrt(252)
        return max(vol, 0.05)  # Minimum 5%

    def calculate_weights(self, price_data: Dict[str, pd.Series]) -> Dict[str, float]:
        """Calculate risk parity weights based on inverse volatility."""
        volatilities = {}
        for symbol, prices in price_data.items():
            volatilities[symbol] = self.calculate_volatility(prices)

        # Inverse volatility weights
        inv_vols = {s: 1.0 / v for s, v in volatilities.items()}
        total_inv_vol = sum(inv_vols.values())

        weights = {s: iv / total_inv_vol for s, iv in inv_vols.items()}

        self.weights = weights
        self.last_rebalance = datetime.now(timezone.utc)

        return weights

    def calculate_adjusted_weights(self, price_data: Dict[str, pd.Series],
                                    correlations: pd.DataFrame = None) -> Dict[str, float]:
        """Calculate weights adjusted for correlations."""
        base_weights = self.calculate_weights(price_data)

        if correlations is not None and len(correlations) > 0:
            # Reduce weight for highly correlated symbols
            adjusted = base_weights.copy()
            symbols = list(base_weights.keys())

            for i, sym1 in enumerate(symbols):
                for sym2 in symbols[i + 1:]:
                    if sym1 in correlations.index and sym2 in correlations.columns:
                        corr = abs(correlations.loc[sym1, sym2])
                        if corr > 0.7:
                            # Reduce both weights by correlation factor
                            reduction = (corr - 0.7) * 0.5
                            adjusted[sym1] *= (1 - reduction)
                            adjusted[sym2] *= (1 - reduction)

            # Renormalize
            total = sum(adjusted.values())
            if total > 0:
                adjusted = {s: w / total for s, w in adjusted.items()}

            return adjusted

        return base_weights

    def get_position_size(self, symbol: str, equity: float, risk_pct: float,
                          price: float, contract_size: int = 100000) -> float:
        """Calculate position size based on risk parity weight."""
        weight = self.weights.get(symbol, 1.0 / len(self.weights) if self.weights else 0.1)

        # Allocate risk based on weight
        risk_amount = equity * risk_pct * weight

        # Convert to lots
        lots = risk_amount / (price * contract_size)

        # Apply limits
        lots = max(lots, 0.01)
        max_lots = (equity * 0.25) / (price * contract_size)
        lots = min(lots, max_lots)

        return round(lots, 2)

    def should_rebalance(self, interval_hours: int = 24) -> bool:
        """Check if rebalancing is needed."""
        if self.last_rebalance is None:
            return True

        elapsed = datetime.now(timezone.utc) - self.last_rebalance
        return elapsed.total_seconds() > interval_hours * 3600

    def get_state(self) -> Dict:
        """Get current risk parity state."""
        return {
            "weights": self.weights,
            "last_rebalance": self.last_rebalance.isoformat() if self.last_rebalance else None,
            "num_symbols": len(self.weights),
        }
