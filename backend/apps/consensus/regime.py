from enum import Enum
from dataclasses import dataclass


class Regime(Enum):
    TRENDING = "trending"
    CHOP = "chop"
    TRAP = "trap"
    ADVERSE_SELECTION = "adverse_selection"
    NORMAL = "normal"


@dataclass
class RegimeResult:
    regime: Regime
    blocked: bool
    reason: str
    confidence: float


class MarketRegimeDetector:
    ADX_CHOP_THRESHOLD = 20.0
    ADX_TREND_THRESHOLD = 25.0
    HIGH_VOLATILITY_PERCENTILE = 0.85
    MAX_SPREAD_BPS = 10.0
    MAX_VOLUME_IMBALANCE = 0.7

    def detect(
        self,
        adx: float = 25.0,
        atr_percentile: float = 0.5,
        price_range_pct: float = 0.005,
        recent_breakout_failed: bool = False,
        spread_bps: float = 5.0,
        volume_imbalance: float = 0.5,
        slippage_bps: float = 2.0,
    ) -> RegimeResult:
        # Check adverse selection first (most dangerous)
        if (
            spread_bps > self.MAX_SPREAD_BPS
            and volume_imbalance > self.MAX_VOLUME_IMBALANCE
        ):
            return RegimeResult(
                regime=Regime.ADVERSE_SELECTION,
                blocked=True,
                reason=f"Adverse selection: spread={spread_bps:.1f}bps, imbalance={volume_imbalance:.2f}",
                confidence=0.9,
            )

        # Check trap (high volatility + failed breakout)
        if (
            atr_percentile > self.HIGH_VOLATILITY_PERCENTILE
            and recent_breakout_failed
        ):
            return RegimeResult(
                regime=Regime.TRAP,
                blocked=True,
                reason=f"Trap detected: high volatility ({atr_percentile:.0f}th pctile) + failed breakout",
                confidence=0.85,
            )

        # Check chop (low ADX)
        if adx < self.ADX_CHOP_THRESHOLD:
            return RegimeResult(
                regime=Regime.CHOP,
                blocked=True,
                reason=f"Choppy market: ADX={adx:.1f} < {self.ADX_CHOP_THRESHOLD}",
                confidence=0.8,
            )

        # Check trending (high ADX)
        if adx >= self.ADX_TREND_THRESHOLD:
            return RegimeResult(
                regime=Regime.TRENDING,
                blocked=False,
                reason=f"Trending market: ADX={adx:.1f} >= {self.ADX_TREND_THRESHOLD}",
                confidence=0.85,
            )

        # Normal market
        return RegimeResult(
            regime=Regime.NORMAL,
            blocked=False,
            reason=f"Normal market conditions: ADX={adx:.1f}",
            confidence=0.7,
        )
