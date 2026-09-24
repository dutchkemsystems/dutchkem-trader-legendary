"""Hedging strategies module.

Provides correlation-based hedging and Gold Hedge EA.
"""

from .correlation import CorrelationHedge
from .hedge_basket import HedgeBasketManager, BasketState
from .gold_hedge_ea import GoldHedgeEA, GoldHedgeIntegration

__all__ = [
    'CorrelationHedge',
    'HedgeBasketManager',
    'BasketState',
    'GoldHedgeEA',
    'GoldHedgeIntegration',
]
