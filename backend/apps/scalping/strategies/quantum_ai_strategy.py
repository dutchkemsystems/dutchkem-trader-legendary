"""Quantum AI Strategy — Combined MT4-inspired scalping strategy.

Wraps Quantum AI (12 weights), Market Memory, Perceptron ML, and VSA
into a single ScalpingStrategy that integrates with the ScalpingEngine.

Entry conditions:
1. Quantum AI score > threshold (weighted multi-factor analysis)
2. VSA confirms direction (volume spread analysis)
3. Perceptron ML agrees (neural network prediction)
4. Market Memory shows positive historical precedent (optional boost)
"""

import logging
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd

from ..base import ScalpingStrategy
from ..signals import ScalpSignal, SignalDirection

log = logging.getLogger(__name__)


class QuantumAIStrategy(ScalpingStrategy):
    """Quantum AI strategy combining 12-weight scoring, VSA, Perceptron, and Market Memory.
    
    This is the "ultimate" strategy imported from MT4's Ultimate AI v24.004
    and GrokUltimateForexPro, adapted for the Dutchkem Trader architecture.
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        
        # Lazy-load modules to avoid circular imports
        self._quantum_ai = None
        self._market_memory = None
        self._perceptron = None
        self._vsa = None
        
        # Strategy parameters
        self.min_quantum_score = config.get('min_quantum_score', 0.3)
        self.min_confidence = config.get('min_confidence', 0.6)
        self.require_vsa = config.get('require_vsa', True)
        self.require_perceptron = config.get('require_perceptron', True)
        self.memory_boost = config.get('memory_boost', 0.1)
    
    def _init_modules(self):
        """Lazy-initialize all sub-modules."""
        if self._quantum_ai is not None:
            return
        
        import os
        base_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
        
        try:
            from apps.ml.quantum_ai import QuantumAI
            self._quantum_ai = QuantumAI(
                persistence_path=os.path.join(base_path, 'quantum_weights.json')
            )
        except Exception as e:
            log.warning(f"QuantumAI init failed: {e}")
            from apps.ml.quantum_ai import QuantumAI
            self._quantum_ai = QuantumAI()
        
        try:
            from apps.ml.market_memory import MarketMemory
            self._market_memory = MarketMemory(
                persistence_path=os.path.join(base_path, 'market_memory.json')
            )
        except Exception as e:
            log.warning(f"MarketMemory init failed: {e}")
            from apps.ml.market_memory import MarketMemory
            self._market_memory = MarketMemory()
        
        try:
            from apps.ml.perceptron import PerceptronModel
            self._perceptron = PerceptronModel(
                mode='simple',
                model_path=os.path.join(base_path, 'perceptron_model.pkl')
            )
        except Exception as e:
            log.warning(f"Perceptron init failed: {e}")
            from apps.ml.perceptron import PerceptronModel
            self._perceptron = PerceptronModel(mode='simple')
        
        try:
            from apps.volume.vsa import VSADetector
            self._vsa = VSADetector()
        except Exception as e:
            log.warning(f"VSA init failed: {e}")
            from apps.volume.vsa import VSADetector
            self._vsa = VSADetector()
    
    def required_timeframes(self) -> List[str]:
        """Need H4 for trend context and M15 for entries."""
        return ['H4', 'M15']
    
    def analyze(self, symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[ScalpSignal]:
        """Analyze market using Quantum AI system.
        
        Args:
            symbol: Trading symbol
            data: Dict with 'H4' and 'M15' DataFrames
            
        Returns:
            ScalpSignal if valid setup found, None otherwise
        """
        self._init_modules()
        
        h4_data = data.get('H4')
        m15_data = data.get('M15')
        
        if h4_data is None or m15_data is None:
            return None
        
        if len(m15_data) < 50:
            return None
        
        # Step 1: Quantum AI scoring (on M15)
        quantum_score = self._quantum_ai.score(m15_data, {'symbol': symbol})
        
        if quantum_score.direction == 'HOLD':
            return None
        
        if abs(quantum_score.score) < self.min_quantum_score:
            return None
        
        # Step 2: VSA confirmation
        vsa_confirms = True
        if self.require_vsa:
            vsa_confirms = self._vsa.confirm_entry(
                m15_data, quantum_score.direction, lookback=5
            )
            if not vsa_confirms:
                return None
        
        # Step 3: Perceptron ML confirmation
        perceptron_agrees = True
        if self.require_perceptron and self._perceptron.trained:
            features = self._extract_perceptron_features(m15_data)
            if features is not None:
                pred = self._perceptron.predict(features)
                if pred.direction == 'UP' and quantum_score.direction == 'SELL':
                    perceptron_agrees = False
                elif pred.direction == 'DOWN' and quantum_score.direction == 'BUY':
                    perceptron_agrees = False
        
        if not perceptron_agrees:
            return None
        
        # Step 4: Market Memory boost
        memory_boost = 0.0
        if self._market_memory:
            recalls = self._market_memory.recall(m15_data, symbol=symbol, top_n=3)
            if recalls:
                # Check if similar patterns were profitable
                win_count = sum(1 for r in recalls if r.predicted_outcome == 'win')
                if win_count > len(recalls) / 2:
                    memory_boost = self.memory_boost
                elif win_count < len(recalls) / 2:
                    memory_boost = -self.memory_boost
        
        # Step 5: H4 trend confirmation
        h4_trend = self._get_h4_trend(h4_data)
        
        # Step 6: Calculate final confidence
        confidence = quantum_score.confidence
        if vsa_confirms:
            confidence += 0.1
        if perceptron_agrees:
            confidence += 0.05
        confidence += memory_boost
        confidence = min(max(confidence, 0.0), 1.0)
        
        if confidence < self.min_confidence:
            return None
        
        # Step 7: Build signal
        entry_price = m15_data['close'].iloc[-1]
        tp_pips = self.config.get('tp_pips', 15)
        sl_pips = self.config.get('sl_pips', 10)
        
        direction = SignalDirection.BUY if quantum_score.direction == 'BUY' else SignalDirection.SELL
        
        # Build reason
        reasons = [f"QAI={quantum_score.score:.2f}"]
        if vsa_confirms:
            reasons.append('VSA')
        if perceptron_agrees:
            reasons.append('ML')
        if memory_boost > 0:
            reasons.append('Mem+')
        elif memory_boost < 0:
            reasons.append('Mem-')
        if h4_trend:
            reasons.append(f'H4={h4_trend}')
        
        return ScalpSignal(
            direction=direction,
            symbol=symbol,
            strategy_name='quantum_ai',
            entry_price=entry_price,
            sl_pips=sl_pips,
            tp_pips=tp_pips,
            confidence=round(confidence, 3),
            reason=f"QuantumAI: {'+'.join(reasons)}",
            metadata={
                'quantum_score': quantum_score.score,
                'quantum_direction': quantum_score.direction,
                'factor_scores': quantum_score.factor_scores,
                'weights': quantum_score.weights,
                'vsa_confirms': vsa_confirms,
                'perceptron_agrees': perceptron_agrees,
                'memory_boost': memory_boost,
                'h4_trend': h4_trend,
            }
        )
    
    def _get_h4_trend(self, h4_data: pd.DataFrame) -> Optional[str]:
        """Determine H4 trend."""
        if len(h4_data) < 50:
            return None
        
        close = h4_data['close']
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        
        price = close.iloc[-1]
        e20, e50 = ema20.iloc[-1], ema50.iloc[-1]
        
        if price > e20 > e50:
            return 'BUY'
        elif price < e20 < e50:
            return 'SELL'
        return None
    
    def _extract_perceptron_features(self, candles: pd.DataFrame) -> Optional[np.ndarray]:
        """Extract 5 features for perceptron (GrokUltimateForexPro style)."""
        if len(candles) < 20:
            return None
        
        close = candles['close']
        
        # 1. RSI normalized
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(com=13, min_periods=14).mean()
        avg_loss = loss.ewm(com=13, min_periods=14).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        rsi_norm = (rsi.iloc[-1] - 50) / 50  # -1 to 1
        
        # 2. MA difference
        ma20 = close.rolling(20).mean()
        ma_diff = (close.iloc[-1] - ma20.iloc[-1]) / (close.iloc[-1] + 1e-10)
        
        # 3. Volume ratio
        if 'volume' in candles.columns:
            vol = candles['volume']
            vol_ratio = vol.iloc[-1] / (vol.rolling(20).mean().iloc[-1] + 1e-10)
        else:
            vol_ratio = 1.0
        
        # 4. S/R distance
        highs = candles['high'].rolling(20).max()
        lows = candles['low'].rolling(20).min()
        resistance = highs.iloc[-1]
        support = lows.iloc[-1]
        sr_range = resistance - support
        if sr_range > 0:
            sr_distance = (close.iloc[-1] - support) / sr_range * 2 - 1  # -1 to 1
        else:
            sr_distance = 0.0
        
        # 5. Momentum
        if len(close) >= 5:
            momentum = (close.iloc[-1] - close.iloc[-5]) / (close.iloc[-5] + 1e-10)
        else:
            momentum = 0.0
        
        return np.array([
            rsi_norm,
            np.clip(ma_diff * 10, -1, 1),
            np.clip(vol_ratio - 1, -1, 1),
            np.clip(sr_distance, -1, 1),
            np.clip(momentum * 10, -1, 1),
        ])
    
    def validate_signal(self, signal: ScalpSignal) -> bool:
        """Validate signal quality."""
        if signal.confidence < self.min_confidence:
            return False
        
        # Check metadata for minimum confluence
        meta = signal.metadata
        confluence = sum([
            1 if meta.get('vsa_confirms') else 0,
            1 if meta.get('perceptron_agrees') else 0,
            1 if meta.get('h4_trend') else 0,
        ])
        
        return confluence >= 2  # Need at least 2 confirmations
