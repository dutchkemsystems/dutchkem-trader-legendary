"""Multi-Pair Gold Hedging — Portfolio-level gold risk management.

Inspired by GoldStuff EA from MT4. Manages gold exposure across
13 currency pairs simultaneously, not just XAUUSD.

Tracks gold-denominated pairs and correlates their movements
to provide portfolio-level hedging.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Gold-denominated pairs and their gold correlation
GOLD_PAIRS = {
    'XAUUSD': {'correlation': 1.0, 'pip_value': 0.01, 'description': 'Direct gold'},
    'EURXAU': {'correlation': 0.85, 'pip_value': 0.01, 'description': 'EUR/Gold'},
    'GBPXAU': {'correlation': 0.80, 'pip_value': 0.01, 'description': 'GBP/Gold'},
    'AUDXAU': {'correlation': 0.75, 'pip_value': 0.01, 'description': 'AUD/Gold'},
    'NZDXAU': {'correlation': 0.70, 'pip_value': 0.01, 'description': 'NZD/Gold'},
    'USDXAU': {'correlation': -0.90, 'pip_value': 0.01, 'description': 'USD/Gold (inverse)'},
    'CADXAU': {'correlation': 0.65, 'pip_value': 0.01, 'description': 'CAD/Gold'},
    'CHFXAU': {'correlation': 0.60, 'pip_value': 0.01, 'description': 'CHF/Gold'},
    'JPYXAU': {'correlation': 0.55, 'pip_value': 0.01, 'description': 'JPY/Gold'},
    # Gold-correlated forex pairs
    'EURUSD': {'correlation': 0.40, 'pip_value': 0.0001, 'description': 'EUR/USD (gold proxy)'},
    'GBPUSD': {'correlation': 0.35, 'pip_value': 0.0001, 'description': 'GBP/USD (gold proxy)'},
    'AUDUSD': {'correlation': 0.45, 'pip_value': 0.0001, 'description': 'AUD/USD (commodity)'},
    'NZDUSD': {'correlation': 0.30, 'pip_value': 0.0001, 'description': 'NZD/USD (commodity)'},
}

# Magic numbers for multi-pair gold (234030-234039)
MULTI_PAIR_GOLD_MAGIC_BASE = 234030


@dataclass
class GoldExposure:
    """Gold exposure for a single pair."""
    symbol: str
    direction: str  # 'BUY', 'SELL', 'NONE'
    lots: float
    notional_usd: float
    gold_equivalent: float  # Notional adjusted by correlation
    correlation: float


@dataclass
class PortfolioExposure:
    """Total gold portfolio exposure."""
    total_gold_exposure: float  # Net gold-equivalent exposure
    long_exposure: float
    short_exposure: float
    net_exposure: float  # long - short
    diversification_score: float  # 0-1 (1 = well diversified)
    pair_exposures: Dict[str, GoldExposure]


class MultiPairGoldHedge:
    """Multi-pair gold hedging system.
    
    Tracks gold exposure across 13 pairs and provides:
    - Portfolio-level gold exposure calculation
    - Correlation-based hedge recommendations
    - Per-symbol hedge entry/exit signals
    
    Usage:
        hedge = MultiPairGoldHedge()
        
        # Check each pair
        for symbol in GOLD_PAIRS:
            signal = hedge.check_pair(symbol, candles[symbol])
            if signal:
                execute(signal)
        
        # Get portfolio view
        exposure = hedge.get_portfolio_exposure()
    """
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize multi-pair gold hedge.
        
        Args:
            config: Configuration dict with:
                - max_net_exposure_usd: Max net gold exposure (default: 10000)
                - hedge_trigger_pct: Trigger hedge when exposure > X% of max (default: 0.8)
                - pairs: List of pairs to track (default: all GOLD_PAIRS)
        """
        self.config = config or {}
        self.max_net_exposure = self.config.get('max_net_exposure_usd', 10000)
        self.hedge_trigger_pct = self.config.get('hedge_trigger_pct', 0.8)
        
        # Track active positions per symbol
        self.positions: Dict[str, Dict] = {}
        
        # Per-symbol configs
        self.pair_configs: Dict[str, Dict] = {}
        for symbol, info in GOLD_PAIRS.items():
            self.pair_configs[symbol] = {
                'correlation': info['correlation'],
                'pip_value': info['pip_value'],
                'lot_progression': [0.01, 0.02, 0.03, 0.05, 0.08],
                'max_hedge_levels': 5,
                'hedge_distance_pips': 50,
                'tp_pips': 30,
                'sl_pips': 40,
            }
        
        # Override with custom config
        if 'pair_overrides' in self.config:
            for symbol, overrides in self.config['pair_overrides'].items():
                if symbol in self.pair_configs:
                    self.pair_configs[symbol].update(overrides)
    
    def check_pair(self, symbol: str, candles: pd.DataFrame) -> Optional[Dict]:
        """Check a pair for hedge signals.
        
        Args:
            symbol: Trading symbol
            candles: OHLCV DataFrame
            
        Returns:
            Signal dict or None
        """
        if symbol not in GOLD_PAIRS:
            return None
        
        if candles is None or len(candles) < 30:
            return None
        
        close = candles['close']
        current_price = close.iloc[-1]
        
        # Calculate indicators
        ema_fast = close.ewm(span=20, adjust=False).mean()
        ema_slow = close.ewm(span=50, adjust=False).mean()
        
        rsi = self._calculate_rsi(close, 14)
        current_rsi = rsi.iloc[-1]
        
        trend = self._get_trend(current_price, ema_fast.iloc[-1], ema_slow.iloc[-1])
        
        # Check current position
        has_position = symbol in self.positions
        
        if has_position:
            return self._check_hedge(symbol, current_price, trend)
        else:
            return self._check_entry(symbol, current_price, current_rsi, trend)
    
    def _get_trend(self, price: float, ema_fast: float, ema_slow: float) -> str:
        """Determine trend direction."""
        if price > ema_fast > ema_slow:
            return 'BUY'
        elif price < ema_fast < ema_slow:
            return 'SELL'
        return 'NEUTRAL'
    
    def _check_entry(
        self, symbol: str, price: float, rsi: float, trend: str
    ) -> Optional[Dict]:
        """Check for initial entry."""
        if trend == 'NEUTRAL':
            return None
        
        # RSI filter
        if rsi > 70 or rsi < 30:
            return None
        
        config = self.pair_configs.get(symbol, {})
        lots = config.get('lot_progression', [0.01])[0]
        correlation = GOLD_PAIRS.get(symbol, {}).get('correlation', 1.0)
        
        return {
            'action': 'OPEN',
            'symbol': symbol,
            'direction': trend,
            'lots': lots,
            'price': price,
            'rsi': rsi,
            'correlation': correlation,
            'gold_equivalent': lots * 100000 * correlation,  # Approximate
            'reason': f'MULTI_GOLD: {symbol} {trend} (RSI={rsi:.1f}, corr={correlation:.2f})',
            'magic': MULTI_PAIR_GOLD_MAGIC_BASE + list(GOLD_PAIRS.keys()).index(symbol) % 10,
        }
    
    def _check_hedge(self, symbol: str, price: float, trend: str) -> Optional[Dict]:
        """Check if hedge should be added."""
        pos = self.positions.get(symbol)
        if not pos:
            return None
        
        config = self.pair_configs.get(symbol, {})
        hedge_distance = config.get('hedge_distance_pips', 50)
        pip_value = config.get('pip_value', 0.0001)
        
        # Calculate distance from entry
        distance_pips = abs(price - pos['entry_price']) / pip_value
        
        # Add hedge if price moved against us
        if distance_pips >= hedge_distance:
            level = pos.get('level', 0) + 1
            progression = config.get('lot_progression', [0.01, 0.02, 0.03, 0.05, 0.08])
            idx = level - 1
            lots = progression[idx] if idx < len(progression) else progression[-1] * 1.5
            
            hedge_direction = 'SELL' if pos['direction'] == 'BUY' else 'BUY'
            
            return {
                'action': 'ADD_HEDGE',
                'symbol': symbol,
                'direction': hedge_direction,
                'lots': lots,
                'price': price,
                'level': level,
                'reason': f'MULTI_GOLD: {symbol} Hedge L{level} (dist={distance_pips:.0f}pips)',
                'magic': MULTI_PAIR_GOLD_MAGIC_BASE + list(GOLD_PAIRS.keys()).index(symbol) % 10,
            }
        
        # Check TP
        tp_pips = config.get('tp_pips', 30)
        if distance_pips >= tp_pips and trend != pos['direction']:
            return {
                'action': 'CLOSE',
                'symbol': symbol,
                'reason': f'MULTI_GOLD: {symbol} TP hit ({distance_pips:.0f}pips)',
                'magic': MULTI_PAIR_GOLD_MAGIC_BASE + list(GOLD_PAIRS.keys()).index(symbol) % 10,
            }
        
        return None
    
    def get_portfolio_exposure(self) -> PortfolioExposure:
        """Calculate total gold portfolio exposure."""
        long_exposure = 0.0
        short_exposure = 0.0
        pair_exposures = {}
        
        for symbol, pos in self.positions.items():
            correlation = GOLD_PAIRS.get(symbol, {}).get('correlation', 1.0)
            notional = pos.get('lots', 0) * 100000  # Standard lot = 100k units
            gold_equiv = notional * abs(correlation)
            
            direction = pos.get('direction', 'NONE')
            if direction == 'BUY':
                long_exposure += gold_equiv
            elif direction == 'SELL':
                short_exposure += gold_equiv
            
            pair_exposures[symbol] = GoldExposure(
                symbol=symbol,
                direction=direction,
                lots=pos.get('lots', 0),
                notional_usd=notional,
                gold_equivalent=gold_equiv,
                correlation=correlation,
            )
        
        net_exposure = long_exposure - short_exposure
        
        # Diversification score: how many different pairs are used
        active_pairs = len(self.positions)
        max_pairs = len(GOLD_PAIRS)
        diversification = min(active_pairs / 5.0, 1.0)  # 5+ pairs = max diversification
        
        return PortfolioExposure(
            total_gold_exposure=long_exposure + short_exposure,
            long_exposure=long_exposure,
            short_exposure=short_exposure,
            net_exposure=net_exposure,
            diversification_score=diversification,
            pair_exposures=pair_exposures,
        )
    
    def should_hedge_portfolio(self) -> Optional[Dict]:
        """Check if portfolio-level hedge is needed."""
        exposure = self.get_portfolio_exposure()
        
        if exposure.total_gold_exposure > self.max_net_exposure * self.hedge_trigger_pct:
            # Portfolio is over-exposed to gold
            # Recommend hedging the most correlated pair
            if exposure.net_exposure > 0:
                # Over-long gold, recommend selling the most correlated pair
                hedge_pair = max(
                    GOLD_PAIRS.items(),
                    key=lambda x: x[1]['correlation']
                )[0]
                return {
                    'action': 'PORTFOLIO_HEDGE',
                    'symbol': hedge_pair,
                    'direction': 'SELL',
                    'reason': f'Portfolio over-exposed to gold (net=${exposure.net_exposure:.0f})',
                    'exposure': exposure,
                }
            else:
                # Over-short gold, recommend buying
                hedge_pair = max(
                    GOLD_PAIRS.items(),
                    key=lambda x: x[1]['correlation']
                )[0]
                return {
                    'action': 'PORTFOLIO_HEDGE',
                    'symbol': hedge_pair,
                    'direction': 'BUY',
                    'reason': f'Portfolio over-exposed to gold short (net=${exposure.net_exposure:.0f})',
                    'exposure': exposure,
                }
        
        return None
    
    def update_position(self, symbol: str, direction: str, lots: float, price: float, level: int = 1):
        """Update tracked position."""
        self.positions[symbol] = {
            'direction': direction,
            'lots': lots,
            'entry_price': price,
            'level': level,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
    
    def close_position(self, symbol: str):
        """Remove tracked position."""
        if symbol in self.positions:
            del self.positions[symbol]
    
    def get_status(self) -> Dict:
        """Get status for API/dashboard."""
        exposure = self.get_portfolio_exposure()
        return {
            'active_pairs': len(self.positions),
            'total_pairs': len(GOLD_PAIRS),
            'long_exposure': exposure.long_exposure,
            'short_exposure': exposure.short_exposure,
            'net_exposure': exposure.net_exposure,
            'diversification': exposure.diversification_score,
            'positions': {
                sym: {
                    'direction': pos['direction'],
                    'lots': pos['lots'],
                    'entry': pos['entry_price'],
                }
                for sym, pos in self.positions.items()
            },
        }
    
    @staticmethod
    def _calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI."""
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        return 100 - (100 / (1 + rs))
