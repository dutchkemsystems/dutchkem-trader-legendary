from dataclasses import dataclass


@dataclass
class RiskConfig:
    max_position_usd: float = 50000.0
    max_positions_per_market: int = 3
    max_trades_per_hour: int = 5
    max_daily_loss_pct: float = 5.0
    min_edge_after_costs: float = 0.02

    def apply_usd_cap(self, lot_size: float, price: float, symbol: str) -> float:
        notional = lot_size * price * 100000
        if notional > self.max_position_usd:
            return self.max_position_usd / (price * 100000)
        return lot_size

    def check_per_market(self, symbol: str, current_positions: dict) -> bool:
        return current_positions.get(symbol, 0) < self.max_positions_per_market

    def check_hourly_limit(self, recent_trades_count: int) -> bool:
        return recent_trades_count < self.max_trades_per_hour
