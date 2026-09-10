"""
Feature 4: Volume Profile & Order Flow Integration
Uses order book depth and volume profile to identify entry/exit zones.
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class VolumeZone:
    price_level: float
    volume: float
    zone_type: str  # "HVN" or "LVN"
    strength: float


class VolumeProfile:
    """Analyze volume at price levels."""

    def __init__(self, num_bins: int = 50):
        self.num_bins = num_bins

    def calculate(self, prices: pd.Series, volumes: pd.Series) -> List[VolumeZone]:
        """Calculate volume profile from price and volume data."""
        if len(prices) < 10:
            return []

        # Create price bins
        price_min = prices.min()
        price_max = prices.max()
        bins = np.linspace(price_min, price_max, self.num_bins + 1)

        # Calculate volume per price bin
        volume_profile = []
        for i in range(len(bins) - 1):
            mask = (prices >= bins[i]) & (prices < bins[i + 1])
            vol = volumes[mask].sum() if mask.any() else 0
            mid_price = (bins[i] + bins[i + 1]) / 2
            volume_profile.append({"price": mid_price, "volume": vol})

        # Identify HVN and LVN
        volumes_arr = [v["volume"] for v in volume_profile]
        mean_vol = np.mean(volumes_arr)
        std_vol = np.std(volumes_arr)

        zones = []
        for vp in volume_profile:
            if vp["volume"] > mean_vol + std_vol:
                zone_type = "HVN"
                strength = min((vp["volume"] - mean_vol) / std_vol, 3.0)
            elif vp["volume"] < mean_vol - std_vol:
                zone_type = "LVN"
                strength = min((mean_vol - vp["volume"]) / std_vol, 3.0)
            else:
                continue

            zones.append(VolumeZone(
                price_level=vp["price"],
                volume=vp["volume"],
                zone_type=zone_type,
                strength=strength,
            ))

        return sorted(zones, key=lambda z: z.volume, reverse=True)

    def find_nearest_zone(self, current_price: float, zones: List[VolumeZone]) -> Tuple[VolumeZone, float]:
        """Find the nearest volume zone to current price."""
        if not zones:
            return None, float("inf")

        nearest = min(zones, key=lambda z: abs(z.price_level - current_price))
        distance = abs(nearest.price_level - current_price)

        return nearest, distance


class OrderFlowAnalyzer:
    """Analyze order flow imbalance from tick data."""

    def __init__(self):
        selfimbalance_history = []

    def calculate_imbalance(self, bid_volume: float, ask_volume: float) -> float:
        """Calculate order flow imbalance (-1 to 1)."""
        total = bid_volume + ask_volume
        if total == 0:
            return 0
        return (bid_volume - ask_volume) / total

    def get_signal(self, imbalance: float, threshold: float = 0.3) -> Dict:
        """Get trading signal from order flow."""
        if imbalance > threshold:
            return {"direction": "BUY", "strength": imbalance, "source": "order_flow"}
        elif imbalance < -threshold:
            return {"direction": "SELL", "strength": abs(imbalance), "source": "order_flow"}
        else:
            return {"direction": "NEUTRAL", "strength": 0, "source": "order_flow"}


def filter_by_volume(price: float, zones: List[VolumeZone], direction: str) -> Dict:
    """Filter trade based on volume profile zones."""
    if not zones:
        return {"allow": True, "reason": "no_volume_data"}

    profile = VolumeProfile()
    nearest, distance = profile.find_nearest_zone(price, zones)

    if nearest is None:
        return {"allow": True, "reason": "no_zones_found"}

    # Only trade near HVN (support/resistance) or breaking LVN
    if nearest.zone_type == "HVN":
        # Near high-volume node — good for entries
        if distance < price * 0.001:  # Within 0.1%
            return {"allow": True, "reason": f"near_HVN_{nearest.price_level:.5f}"}
    elif nearest.zone_type == "LVN":
        # Breaking through low-volume node — breakout opportunity
        if distance < price * 0.002:  # Within 0.2%
            return {"allow": True, "reason": f"near_LVN_breakout_{nearest.price_level:.5f}"}

    return {"allow": False, "reason": f"away_from_volume_zones"}
