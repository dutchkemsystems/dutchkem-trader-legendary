"""Market Memory Module — Pattern Fingerprinting and Recall.

Inspired by Ultimate AI v24.004 from MT4. Stores recent candlestick patterns
with their outcomes, and recalls similar setups to predict future price action.

"How have we seen this pattern before? What happened last time?"
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

# Maximum patterns to store
MAX_PATTERNS = 1000
# Pattern length (bars)
PATTERN_LENGTH = 20
# Minimum similarity threshold for recall
SIMILARITY_THRESHOLD = 0.7


@dataclass
class PatternFingerprint:
    """A fingerprinted candlestick pattern."""
    pattern_id: str
    features: List[float]  # Normalized feature vector
    outcome: Optional[str] = None  # 'win', 'loss', 'breakeven'
    pips: float = 0.0
    direction: str = 'HOLD'
    symbol: str = ''
    timestamp: str = ''
    timeframe: str = ''


@dataclass
class MemoryRecall:
    """Result of a memory recall query."""
    similarity: float  # 0-1
    pattern: PatternFingerprint
    predicted_outcome: str
    confidence: float


class MarketMemory:
    """Pattern fingerprinting and recall system.
    
    Usage:
        memory = MarketMemory()
        
        # After a trade closes:
        memory.store(candles, outcome='win', pips=15.0, direction='BUY')
        
        # Before entering a trade:
        recalls = memory.recall(current_candles)
        if recalls and recalls[0].confidence > 0.7:
            # Similar pattern was profitable before
    """
    
    def __init__(self, persistence_path: str = None, max_patterns: int = MAX_PATTERNS):
        """Initialize Market Memory.
        
        Args:
            persistence_path: Path to save/load patterns
            max_patterns: Maximum patterns to store (FIFO eviction)
        """
        self.persistence_path = persistence_path
        self.max_patterns = max_patterns
        self.patterns: List[PatternFingerprint] = []
        
        if persistence_path and os.path.exists(persistence_path):
            self._load()
    
    def store(
        self,
        candles: pd.DataFrame,
        outcome: str,
        pips: float = 0.0,
        direction: str = 'HOLD',
        symbol: str = '',
        timeframe: str = '',
    ):
        """Store a new pattern with its outcome.
        
        Args:
            candles: OHLCV DataFrame (at least PATTERN_LENGTH bars)
            outcome: 'win', 'loss', or 'breakeven'
            pips: Profit/loss in pips
            direction: Trade direction ('BUY'/'SELL')
            symbol: Symbol traded
            timeframe: Timeframe of candles
        """
        if candles is None or len(candles) < PATTERN_LENGTH:
            return
        
        features = self._fingerprint(candles)
        
        pattern = PatternFingerprint(
            pattern_id=self._generate_id(features),
            features=features,
            outcome=outcome,
            pips=pips,
            direction=direction,
            symbol=symbol,
            timestamp=datetime.now(timezone.utc).isoformat(),
            timeframe=timeframe,
        )
        
        self.patterns.append(pattern)
        
        # Evict oldest if over limit
        if len(self.patterns) > self.max_patterns:
            self.patterns = self.patterns[-self.max_patterns:]
        
        # Persist
        if self.persistence_path:
            self._save()
        
        log.info(f"MarketMemory: Stored pattern {pattern.pattern_id[:8]}... "
                 f"outcome={outcome} pips={pips:.1f}")
    
    def recall(
        self,
        candles: pd.DataFrame,
        symbol: str = '',
        top_n: int = 3,
    ) -> List[MemoryRecall]:
        """Recall similar patterns from memory.
        
        Args:
            candles: Current OHLCV DataFrame
            symbol: Symbol to filter by (optional)
            top_n: Number of top matches to return
            
        Returns:
            List of MemoryRecall, sorted by similarity (best first)
        """
        if candles is None or len(candles) < PATTERN_LENGTH:
            return []
        
        if not self.patterns:
            return []
        
        current_features = self._fingerprint(candles)
        
        # Calculate similarity to all stored patterns
        candidates = []
        for pat in self.patterns:
            # Optionally filter by symbol
            if symbol and pat.symbol and pat.symbol != symbol:
                continue
            
            similarity = self._cosine_similarity(current_features, pat.features)
            
            if similarity >= SIMILARITY_THRESHOLD:
                # Predict outcome based on historical
                outcome_counts = {'win': 0, 'loss': 0, 'breakeven': 0}
                # Find all similar patterns
                for p in self.patterns:
                    sim = self._cosine_similarity(current_features, p.features)
                    if sim >= SIMILARITY_THRESHOLD and p.outcome:
                        outcome_counts[p.outcome] = outcome_counts.get(p.outcome, 0) + 1
                
                total = sum(outcome_counts.values())
                if total > 0:
                    predicted = max(outcome_counts, key=outcome_counts.get)
                    confidence = outcome_counts[predicted] / total
                else:
                    predicted = 'breakeven'
                    confidence = 0.0
                
                candidates.append(MemoryRecall(
                    similarity=similarity,
                    pattern=pat,
                    predicted_outcome=predicted,
                    confidence=confidence,
                ))
        
        # Sort by similarity
        candidates.sort(key=lambda r: r.similarity, reverse=True)
        
        return candidates[:top_n]
    
    def get_win_rate(self, symbol: str = '') -> float:
        """Get overall win rate from stored patterns."""
        relevant = [p for p in self.patterns if p.outcome]
        if symbol:
            relevant = [p for p in relevant if p.symbol == symbol]
        
        if not relevant:
            return 0.5  # Default 50%
        
        wins = sum(1 for p in relevant if p.outcome == 'win')
        return wins / len(relevant)
    
    def get_stats(self) -> Dict:
        """Get memory statistics."""
        outcomes = [p.outcome for p in self.patterns if p.outcome]
        return {
            'total_patterns': len(self.patterns),
            'with_outcomes': len(outcomes),
            'win_rate': sum(1 for o in outcomes if o == 'win') / max(len(outcomes), 1),
            'avg_pips': np.mean([p.pips for p in self.patterns if p.pips]) if self.patterns else 0,
        }
    
    # ─── Fingerprinting ───────────────────────────────────────────────
    
    def _fingerprint(self, candles: pd.DataFrame) -> List[float]:
        """Create a normalized feature vector from candles.
        
        Uses the last PATTERN_LENGTH bars and extracts:
        - Relative OHLC positions (4 features)
        - Body size ratios (1 feature)
        - Shadow ratios (2 features)
        - Price change sequence (5 features)
        - Volatility sequence (3 features)
        - Volume sequence (3 features)
        Total: 18 features
        """
        data = candles.tail(PATTERN_LENGTH).copy()
        close = data['close'].values
        open_ = data['open'].values
        high = data['high'].values
        low = data['low'].values
        
        features = []
        
        # 1. Relative close position (0-1, where in the bar's range)
        ranges = high - low
        ranges[ranges == 0] = 1  # Avoid division by zero
        close_pos = (close - low) / ranges
        features.extend(close_pos[-5:].tolist())  # Last 5 bars
        
        # 2. Body size ratio (body / range)
        bodies = np.abs(close - open_)
        body_ratios = bodies / ranges
        features.extend(body_ratios[-5:].tolist())
        
        # 3. Shadow ratios
        upper_shadows = (high - np.maximum(close, open_)) / ranges
        lower_shadows = (np.minimum(close, open_) - low) / ranges
        features.append(np.mean(upper_shadows[-5:]))
        features.append(np.mean(lower_shadows[-5:]))
        
        # 4. Price change sequence (normalized)
        price_changes = np.diff(close) / (close[:-1] + 1e-10)
        features.extend(price_changes[-5:].tolist() if len(price_changes) >= 5 
                       else [0.0] * 5)
        
        # 5. Volatility sequence (ATR-like)
        tr = np.maximum(high - low, 
                       np.maximum(np.abs(high - np.roll(close, 1)),
                                  np.abs(low - np.roll(close, 1))))
        tr = tr[1:]  # Skip first (NaN from roll)
        vol_norm = tr / (close[1:] + 1e-10)
        features.extend(vol_norm[-3:].tolist() if len(vol_norm) >= 3 
                       else [0.0] * 3)
        
        # 6. Volume sequence (if available)
        if 'volume' in candles.columns:
            vol = data['volume'].values
            vol_sma = np.mean(vol) if np.mean(vol) > 0 else 1
            vol_norm = vol / vol_sma
            features.extend(vol_norm[-3:].tolist() if len(vol_norm) >= 3 
                           else [1.0] * 3)
        else:
            features.extend([1.0] * 3)
        
        # Normalize all features to [-1, 1]
        features = np.array(features, dtype=float)
        features = np.clip(features, -1.0, 1.0)
        
        return features.tolist()
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two feature vectors."""
        a = np.array(a, dtype=float)
        b = np.array(b, dtype=float)
        
        # Ensure same length
        min_len = min(len(a), len(b))
        a = a[:min_len]
        b = b[:min_len]
        
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return float(dot / (norm_a * norm_b))
    
    def _generate_id(self, features: List[float]) -> str:
        """Generate a unique ID from features."""
        import hashlib
        feature_str = ','.join(f'{f:.4f}' for f in features[:10])
        return hashlib.md5(feature_str.encode()).hexdigest()[:12]
    
    # ─── Persistence ──────────────────────────────────────────────────
    
    def _save(self):
        """Save patterns to disk."""
        data = []
        for p in self.patterns:
            data.append({
                'pattern_id': p.pattern_id,
                'features': p.features,
                'outcome': p.outcome,
                'pips': p.pips,
                'direction': p.direction,
                'symbol': p.symbol,
                'timestamp': p.timestamp,
                'timeframe': p.timeframe,
            })
        
        os.makedirs(os.path.dirname(self.persistence_path), exist_ok=True)
        with open(self.persistence_path, 'w') as f:
            json.dump(data, f)
    
    def _load(self):
        """Load patterns from disk."""
        try:
            with open(self.persistence_path, 'r') as f:
                data = json.load(f)
            
            self.patterns = []
            for d in data:
                self.patterns.append(PatternFingerprint(
                    pattern_id=d.get('pattern_id', ''),
                    features=d.get('features', []),
                    outcome=d.get('outcome'),
                    pips=d.get('pips', 0),
                    direction=d.get('direction', 'HOLD'),
                    symbol=d.get('symbol', ''),
                    timestamp=d.get('timestamp', ''),
                    timeframe=d.get('timeframe', ''),
                ))
            
            log.info(f"MarketMemory: Loaded {len(self.patterns)} patterns")
        except Exception as e:
            log.warning(f"MarketMemory: Failed to load: {e}")
            self.patterns = []
