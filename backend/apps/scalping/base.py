"""Base class for all scalping strategies."""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
import pandas as pd

from .signals import ScalpSignal, SignalDirection


class ScalpingStrategy(ABC):
    """Base class for all scalping strategies.
    
    Each strategy must implement:
    - analyze(): Generate a signal from market data
    - required_timeframes(): List of timeframes needed
    
    Optional overrides:
    - validate_signal(): Pre-execution validation
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize strategy with configuration.
        
        Args:
            config: Strategy-specific configuration dict
        """
        self.config = config
        self._enabled = config.get('enabled', False)
    
    @property
    def enabled(self) -> bool:
        """Whether this strategy is enabled."""
        return self._enabled
    
    @abstractmethod
    def analyze(self, symbol: str, data: Dict[str, pd.DataFrame]) -> Optional[ScalpSignal]:
        """Analyze market data and generate a signal.
        
        Args:
            symbol: Trading symbol (e.g., 'EURUSD')
            data: Dict with OHLCV DataFrames for required timeframes
            
        Returns:
            ScalpSignal if signal generated, None otherwise
        """
        pass
    
    @abstractmethod
    def required_timeframes(self) -> List[str]:
        """Return list of timeframes needed (e.g., ['M5', 'M15'])."""
        pass
    
    def validate_signal(self, signal: ScalpSignal) -> bool:
        """Optional validation before signal is sent to risk manager.
        
        Override this to add strategy-specific validation.
        Default: always valid.
        """
        return True
