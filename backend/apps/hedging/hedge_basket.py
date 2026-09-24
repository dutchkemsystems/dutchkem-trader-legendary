"""Hedge Basket — manages multiple positions as a single unit.

Used by Gold Hedge EA to track a basket of hedged positions,
calculate combined P&L, and determine when to close the basket.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Optional
import logging

log = logging.getLogger(__name__)


@dataclass
class HedgeLevel:
    """A single hedge level in the basket."""
    level: int
    direction: str  # BUY or SELL
    lots: float
    entry_price: float
    ticket: int
    entry_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class BasketState:
    """Complete state of a hedge basket."""
    symbol: str
    levels: List[HedgeLevel] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    peak_profit: float = 0.0
    is_frozen: bool = False

    @property
    def total_lots(self) -> float:
        return sum(l.lots for l in self.levels)

    @property
    def current_level(self) -> int:
        return len(self.levels)

    @property
    def directions(self) -> List[str]:
        return [l.direction for l in self.levels]


class HedgeBasketManager:
    """Manages hedge baskets for Gold Hedge EA.
    
    Each basket tracks multiple hedged positions and determines
    when to close based on combined profit targets.
    """

    # Default lot progression: 0.01 → 0.02 → 0.03 → 0.05 → 0.08
    DEFAULT_LOT_PROGRESSION = [0.01, 0.02, 0.03, 0.05, 0.08]

    def __init__(self, config: Dict = None):
        """Initialize basket manager.
        
        Args:
            config: Gold Hedge EA configuration dict
        """
        self.config = config or {}
        self.baskets: Dict[str, BasketState] = {}  # symbol -> basket
        self.lot_progression = self.config.get('lot_progression', self.DEFAULT_LOT_PROGRESSION)
        self.max_hedge_levels = self.config.get('max_hedge_levels', 5)
        self.basket_tp_usd = self.config.get('basket_tp_usd', 50.0)
        self.min_profit_floor_usd = self.config.get('min_profit_floor_usd', 10.0)
        self.freeze_loss_usd = self.config.get('freeze_loss_usd', 200.0)
        self.trailing_tp_enabled = self.config.get('trailing_tp_enabled', True)
        self.trailing_tp_step_usd = self.config.get('trailing_tp_step_usd', 10.0)

    def has_active_basket(self, symbol: str) -> bool:
        """Check if symbol has an active basket."""
        return symbol in self.baskets

    def get_basket(self, symbol: str) -> Optional[BasketState]:
        """Get the basket for a symbol."""
        return self.baskets.get(symbol)

    def create_basket(self, symbol: str, direction: str, entry_price: float, ticket: int) -> BasketState:
        """Create a new basket with initial entry."""
        lots = self.lot_progression[0] if self.lot_progression else 0.01
        
        level = HedgeLevel(
            level=1,
            direction=direction,
            lots=lots,
            entry_price=entry_price,
            ticket=ticket,
        )
        
        basket = BasketState(symbol=symbol, levels=[level])
        self.baskets[symbol] = basket
        
        log.info(f"BASKET CREATED {symbol}: {direction} {lots} lots @ {entry_price} (level 1/{self.max_hedge_levels})")
        return basket

    def add_hedge(self, symbol: str, entry_price: float, ticket: int) -> Optional[HedgeLevel]:
        """Add a hedge level to existing basket.
        
        Returns the new HedgeLevel, or None if max levels reached or basket frozen.
        """
        basket = self.baskets.get(symbol)
        if basket is None:
            return None
        
        if basket.is_frozen:
            log.warning(f"BASKET FROZEN {symbol} — cannot add hedge")
            return None
        
        if basket.current_level >= self.max_hedge_levels:
            log.warning(f"BASKET MAX LEVELS {symbol} — {basket.current_level}/{self.max_hedge_levels}")
            return None
        
        # Determine direction (opposite of last level)
        last_direction = basket.levels[-1].direction
        new_direction = "SELL" if last_direction == "BUY" else "BUY"
        
        # Get lot size from progression
        level_idx = basket.current_level  # 0-indexed (already have 1 level)
        if level_idx < len(self.lot_progression):
            lots = self.lot_progression[level_idx]
        else:
            # Fallback: multiply last lots by multiplier
            last_lots = basket.levels[-1].lots
            multiplier = self.config.get('lot_multiplier', 1.5)
            lots = round(last_lots * multiplier, 2)
        
        level = HedgeLevel(
            level=basket.current_level + 1,
            direction=new_direction,
            lots=lots,
            entry_price=entry_price,
            ticket=ticket,
        )
        
        basket.levels.append(level)
        
        log.info(f"BASKET HEDGE {symbol}: {new_direction} {lots} lots @ {entry_price} "
                 f"(level {level.level}/{self.max_hedge_levels}, basket total: {basket.total_lots} lots)")
        return level

    def calculate_basket_pnl(self, symbol: str, current_prices: Dict[str, float]) -> float:
        """Calculate combined P&L for all positions in the basket.
        
        Args:
            symbol: Symbol name
            current_prices: Dict with 'bid' and 'ask' prices
            
        Returns:
            Combined P&L in account currency
        """
        basket = self.baskets.get(symbol)
        if basket is None:
            return 0.0
        
        total_pnl = 0.0
        bid = current_prices.get('bid', 0.0)
        ask = current_prices.get('ask', 0.0)
        
        for level in basket.levels:
            if level.direction == "BUY":
                pnl = (bid - level.entry_price) * level.lots * self._get_pip_value(symbol)
            else:  # SELL
                pnl = (level.entry_price - ask) * level.lots * self._get_pip_value(symbol)
            total_pnl += pnl
        
        return round(total_pnl, 2)

    def should_close_basket(self, symbol: str, current_pnl: float) -> tuple[bool, str]:
        """Determine if basket should be closed.
        
        Returns:
            (should_close, reason) tuple
        """
        basket = self.baskets.get(symbol)
        if basket is None:
            return False, ""
        
        # Check freeze threshold
        if current_pnl < -self.freeze_loss_usd:
            basket.is_frozen = True
            return True, f"FREEZE: Loss {current_pnl:.2f} exceeds threshold {-self.freeze_loss_usd:.2f}"
        
        # Check hard take-profit
        if current_pnl >= self.basket_tp_usd:
            if current_pnl >= self.min_profit_floor_usd:
                return True, f"TP HIT: Profit {current_pnl:.2f} >= target {self.basket_tp_usd:.2f}"
        
        # Check trailing take-profit
        if self.trailing_tp_enabled and current_pnl > self.min_profit_floor_usd:
            if current_pnl > basket.peak_profit:
                basket.peak_profit = current_pnl
            elif basket.peak_profit - current_pnl >= self.trailing_tp_step_usd:
                return True, f"TRAILING TP: Dropped {basket.peak_profit - current_pnl:.2f} from peak {basket.peak_profit:.2f}"
        
        return False, ""

    def close_basket(self, symbol: str) -> Optional[BasketState]:
        """Close and remove basket. Returns the closed basket state."""
        basket = self.baskets.pop(symbol, None)
        if basket:
            log.info(f"BASKET CLOSED {symbol}: {basket.current_level} levels, "
                     f"peak profit: ${basket.peak_profit:.2f}")
        return basket

    def get_all_baskets(self) -> Dict[str, BasketState]:
        """Return all active baskets."""
        return dict(self.baskets)

    def _get_pip_value(self, symbol: str) -> float:
        """Get pip value for a symbol (rough estimate)."""
        symbol_upper = symbol.upper()
        if 'JPY' in symbol_upper:
            return 100.0  # JPY pairs: 1 pip = 0.01, 100 pips per lot
        elif 'XAU' in symbol_upper:
            return 1.0  # Gold: 1 point = $1 per lot
        else:
            return 10000.0  # Standard forex: 1 pip = 0.0001, 10000 pips per lot
