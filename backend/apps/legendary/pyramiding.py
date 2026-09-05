from typing import Dict, Any, Optional
import pandas as pd
from .seykota import SeykotaTrendModule

class PyramidingLogic:
    def __init__(self):
        self.entry_count = 1
        self.max_entries = 4
        self.increment_percent = 0.3

    def should_add_position(self, position: Dict[str, Any], market_data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        # 1. Must be in profit
        if position.get('profit_pips', 0) < 20:
            return None

        # 2. Trend must still be strong
        seykota = SeykotaTrendModule()
        trend = seykota.analyze_trend(market_data)
        if trend['action'] != position.get('action'):
            return None

        # 3. Not reached max entries
        if self.entry_count >= self.max_entries:
            return None

        # 4. Calculate additional lot size
        base_lot = position.get('lot_size', 0.01)
        additional = base_lot * (1 + self.increment_percent * (self.entry_count - 1))

        self.entry_count += 1

        return {
            'add': True,
            'additional_lot': additional,
            'reason': f'Pyramiding entry #{self.entry_count}'
        }

    def reset(self):
        self.entry_count = 1
