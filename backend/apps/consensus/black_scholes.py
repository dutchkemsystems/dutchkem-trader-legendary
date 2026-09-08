import math
from dataclasses import dataclass
from scipy.stats import norm

@dataclass
class EdgeResult:
    p_up: float
    edge: float
    tradeable: bool
    d2: float
    momentum_adjusted: bool

class BlackScholesEngine:
    DEFAULT_RISK_FREE = 0.05
    DEFAULT_VOLATILITY = 0.15
    DEFAULT_TIME_TO_EXPIRY = 30 / 365
    MIN_EDGE_AFTER_COSTS = 0.02

    def calculate_d2(self, stock_price: float, strike_price: float,
                     risk_free_rate: float = None, volatility: float = None,
                     time_to_expiry: float = None) -> float:
        r = risk_free_rate or self.DEFAULT_RISK_FREE
        sigma = volatility or self.DEFAULT_VOLATILITY
        T = time_to_expiry or self.DEFAULT_TIME_TO_EXPIRY

        d2 = (math.log(stock_price / strike_price) + (r - sigma**2 / 2) * T) / (sigma * math.sqrt(T))
        return d2

    def calculate_p_up(self, stock_price: float, strike_price: float,
                       risk_free_rate: float = None, volatility: float = None,
                       time_to_expiry: float = None) -> float:
        d2 = self.calculate_d2(stock_price, strike_price, risk_free_rate, volatility, time_to_expiry)
        return float(norm.cdf(d2))

    def apply_momentum_adjustment(self, p_base: float, momentum: float, weight: float = 0.1) -> float:
        # logit(p*) = logit(p) + w * tanh(momentum)
        p_clamped = max(0.01, min(0.99, p_base))
        logit_p = math.log(p_clamped / (1 - p_clamped))
        adjusted_logit = logit_p + weight * math.tanh(momentum)
        p_adjusted = 1 / (1 + math.exp(-adjusted_logit))
        return max(0.01, min(0.99, p_adjusted))

    def calculate_edge(self, p_up: float, market_price: float) -> float:
        return p_up - market_price

    def is_tradeable(self, edge: float, min_edge: float = None) -> bool:
        threshold = min_edge or self.MIN_EDGE_AFTER_COSTS
        return edge > threshold

    def evaluate(self, stock_price: float, strike_price: float, market_price: float,
                 momentum: float = 0.0, **kwargs) -> EdgeResult:
        p_up = self.calculate_p_up(stock_price, strike_price, **kwargs)
        p_adjusted = self.apply_momentum_adjustment(p_up, momentum)
        edge = self.calculate_edge(p_adjusted, market_price)
        tradeable = self.is_tradeable(edge)
        d2 = self.calculate_d2(stock_price, strike_price, **kwargs)
        return EdgeResult(
            p_up=p_adjusted,
            edge=edge,
            tradeable=tradeable,
            d2=d2,
            momentum_adjusted=(momentum != 0.0)
        )
