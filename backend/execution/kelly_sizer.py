from decimal import Decimal


class KellySizer:
    QUARTER_KELLY_DIVISOR = 4
    MAX_KELLY_FRACTION = Decimal("0.25")

    def calculate(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        if avg_loss == 0 or avg_win == 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0
        b = avg_win / avg_loss
        p = win_rate
        q = 1 - p
        kelly = (b * p - q) / b
        quarter_kelly = kelly / self.QUARTER_KELLY_DIVISOR
        return max(0.0, min(float(self.MAX_KELLY_FRACTION), quarter_kelly))
