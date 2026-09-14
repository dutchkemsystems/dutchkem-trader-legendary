"""Scalping strategies registry.

All strategies are registered here. The ScalpingEngine reads this
to dynamically load enabled strategies.
"""

from .chiaroscuro import ChiaroscuroStrategy
from .london_ny import LondonNYOverlapStrategy
from .checklist_5pt import FivePointChecklistStrategy
from .autolot import AutoLotStrategy
from .renko import RenkoStrategy
from .sniper import SniperStrategy
from .ema_pullback import EMAPullbackStrategy
from .session_breakout import SessionBreakoutStrategy
from .news_fade import NewsFadeStrategy
from .fvg_confluence import FVGConfluenceStrategy

ALL_STRATEGIES = {
    'chiaroscuro': ChiaroscuroStrategy,
    'london_ny_overlap': LondonNYOverlapStrategy,
    'checklist_5point': FivePointChecklistStrategy,
    'autolot_20pip': AutoLotStrategy,
    'renko_20pip': RenkoStrategy,
    'sniper': SniperStrategy,
    'ema_pullback': EMAPullbackStrategy,
    'session_breakout': SessionBreakoutStrategy,
    'news_fade': NewsFadeStrategy,
    'fvg_confluence': FVGConfluenceStrategy,
}
