# backend/metrics.py
from prometheus_client import Histogram, Gauge, Counter

# Order Metrics
ORDER_LATENCY = Histogram(
    "dutchkem_order_latency_seconds",
    "time from signal to fill",
    ["strategy", "exchange", "side"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)
ORDERS_TOTAL = Counter(
    "dutchkem_orders_total",
    "total orders placed",
    ["strategy", "exchange", "side", "status"],
)
SLIPPAGE_BPS = Histogram(
    "dutchkem_slippage_bps",
    "slippage in basis points",
    ["strategy", "exchange", "side"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 25.0],
)

# Data Feed Metrics
FEED_LATENCY = Gauge(
    "dutchkem_feed_latency_ms",
    "data feed latency in milliseconds",
    ["source", "symbol"],
)
FEED_STALENESS = Gauge(
    "dutchkem_feed_staleness_seconds",
    "seconds since last data update",
    ["source", "symbol"],
)

# Trading Metrics
PNL_TOTAL = Gauge(
    "dutchkem_pnl_total_usd",
    "total PnL in USD",
    ["strategy"],
)
PNL_DAILY = Gauge(
    "dutchkem_pnl_daily_usd",
    "daily PnL in USD",
    ["strategy"],
)
POSITION_SIZE = Gauge(
    "dutchkem_position_size",
    "current position size",
    ["strategy", "symbol"],
)
SIGNAL_COUNT = Counter(
    "dutchkem_signals_total",
    "total signals generated",
    ["strategy", "direction"],
)
CIRCUIT_BREAKER = Gauge(
    "dutchkem_circuit_breaker",
    "circuit breaker state (0=closed, 1=open, 2=half-open)",
    ["strategy"],
)

# System Metrics
CYCLE_DURATION = Histogram(
    "dutchkem_cycle_duration_seconds",
    "trading cycle duration",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)
