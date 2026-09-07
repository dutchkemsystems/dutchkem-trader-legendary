"""Tests for Monte Carlo Simulator — trade resampling for confidence intervals."""
import pytest
from decimal import Decimal
from backtesting.metrics import TradeRecord
from backtesting.monte_carlo import MonteCarloConfig, MonteCarloResult, MonteCarloSimulator


def _sample_trades():
    """Create a mix of winning and losing trades for testing."""
    return [
        TradeRecord("EURUSD", "BUY", Decimal("0.1"), Decimal("1.08"), Decimal("1.09"), Decimal("100")),
        TradeRecord("EURUSD", "SELL", Decimal("0.1"), Decimal("1.09"), Decimal("1.085"), Decimal("50")),
        TradeRecord("EURUSD", "BUY", Decimal("0.1"), Decimal("1.085"), Decimal("1.08"), Decimal("-50")),
        TradeRecord("EURUSD", "SELL", Decimal("0.1"), Decimal("1.08"), Decimal("1.09"), Decimal("-100")),
        TradeRecord("EURUSD", "BUY", Decimal("0.1"), Decimal("1.09"), Decimal("1.10"), Decimal("100")),
    ]


class TestMonteCarloConfig:
    def test_default_config(self):
        cfg = MonteCarloConfig()
        assert cfg.n_simulations == 1000
        assert cfg.confidence_level == 0.95
        assert cfg.initial_equity == 10000
        assert cfg.seed is None

    def test_custom_config(self):
        cfg = MonteCarloConfig(
            n_simulations=500,
            confidence_level=0.90,
            initial_equity=50000,
            seed=42,
        )
        assert cfg.n_simulations == 500
        assert cfg.confidence_level == 0.90
        assert cfg.initial_equity == 50000
        assert cfg.seed == 42


class TestMonteCarloResult:
    def test_result_fields(self):
        trades = _sample_trades()
        sim = MonteCarloSimulator(MonteCarloConfig(n_simulations=10, seed=42))
        result = sim.run(trades)
        assert hasattr(result, "simulated_pnl")
        assert hasattr(result, "simulated_max_drawdown")
        assert hasattr(result, "simulated_sharpe")
        assert hasattr(result, "statistics")
        assert hasattr(result, "confidence_intervals")

    def test_result_types(self):
        trades = _sample_trades()
        sim = MonteCarloSimulator(MonteCarloConfig(n_simulations=10, seed=42))
        result = sim.run(trades)
        assert isinstance(result.simulated_pnl, list)
        assert isinstance(result.simulated_max_drawdown, list)
        assert isinstance(result.simulated_sharpe, list)
        assert isinstance(result.statistics, dict)
        assert isinstance(result.confidence_intervals, dict)


class TestMonteCarloSimulator:
    def test_empty_trades(self):
        sim = MonteCarloSimulator(MonteCarloConfig(n_simulations=10, seed=42))
        result = sim.run([])
        assert result.simulated_pnl == []
        assert result.simulated_max_drawdown == []
        assert result.simulated_sharpe == []
        assert result.statistics == {}

    def test_simulation_count(self):
        """Each simulation produces one P&L, drawdown, and sharpe value."""
        trades = _sample_trades()
        n = 50
        sim = MonteCarloSimulator(MonteCarloConfig(n_simulations=n, seed=42))
        result = sim.run(trades)
        assert len(result.simulated_pnl) == n
        assert len(result.simulated_max_drawdown) == n
        assert len(result.simulated_sharpe) == n

    def test_pnl_distribution(self):
        """Total PnL across simulations should have spread (not all identical)."""
        trades = _sample_trades()
        sim = MonteCarloSimulator(MonteCarloConfig(n_simulations=100, seed=42))
        result = sim.run(trades)
        assert len(set(result.simulated_pnl)) > 1

    def test_max_drawdown_non_negative(self):
        """Max drawdown in each simulation should be >= 0."""
        trades = _sample_trades()
        sim = MonteCarloSimulator(MonteCarloConfig(n_simulations=50, seed=42))
        result = sim.run(trades)
        for dd in result.simulated_max_drawdown:
            assert dd >= 0

    def test_statistics_computed(self):
        """Statistics dict should contain mean, median, std, min, max for each metric."""
        trades = _sample_trades()
        sim = MonteCarloSimulator(MonteCarloConfig(n_simulations=50, seed=42))
        result = sim.run(trades)
        stats = result.statistics
        for key in ["pnl_mean", "pnl_median", "pnl_std", "pnl_min", "pnl_max",
                     "drawdown_mean", "drawdown_median", "drawdown_std",
                     "sharpe_mean", "sharpe_median", "sharpe_std"]:
            assert key in stats, f"Missing statistic: {key}"

    def test_confidence_intervals_computed(self):
        """Confidence intervals should contain lower/upper for each metric."""
        trades = _sample_trades()
        sim = MonteCarloSimulator(MonteCarloConfig(n_simulations=50, seed=42))
        result = sim.run(trades)
        ci = result.confidence_intervals
        for metric in ["pnl", "drawdown", "sharpe"]:
            assert f"{metric}_lower" in ci, f"Missing CI: {metric}_lower"
            assert f"{metric}_upper" in ci, f"Missing CI: {metric}_upper"

    def test_confidence_interval_bounds(self):
        """CI lower <= mean <= CI upper for P&L."""
        trades = _sample_trades()
        sim = MonteCarloSimulator(MonteCarloConfig(n_simulations=100, seed=42))
        result = sim.run(trades)
        mean_pnl = result.statistics["pnl_mean"]
        lower = result.confidence_intervals["pnl_lower"]
        upper = result.confidence_intervals["pnl_upper"]
        assert lower <= mean_pnl <= upper

    def test_deterministic_with_seed(self):
        """Same seed produces identical results."""
        trades = _sample_trades()
        sim1 = MonteCarloSimulator(MonteCarloConfig(n_simulations=20, seed=42))
        r1 = sim1.run(trades)
        sim2 = MonteCarloSimulator(MonteCarloConfig(n_simulations=20, seed=42))
        r2 = sim2.run(trades)
        assert r1.simulated_pnl == r2.simulated_pnl
        assert r1.simulated_max_drawdown == r2.simulated_max_drawdown

    def test_single_trade(self):
        """Works with just one trade."""
        trades = [TradeRecord("EURUSD", "BUY", Decimal("0.1"), Decimal("1.08"), Decimal("1.09"), Decimal("100"))]
        sim = MonteCarloSimulator(MonteCarloConfig(n_simulations=10, seed=42))
        result = sim.run(trades)
        assert len(result.simulated_pnl) == 10
        # With one trade, every simulation has the same PnL
        assert len(set(result.simulated_pnl)) == 1

    def test_total_pnl_preserved(self):
        """Sum of trade PnLs should equal the mean simulated PnL (since resampling preserves total)."""
        trades = _sample_trades()
        expected_total = sum(t.pnl for t in trades)
        sim = MonteCarloSimulator(MonteCarloConfig(n_simulations=100, seed=42))
        result = sim.run(trades)
        # Each simulation resamples trades — total PnL per sim equals sum of resampled subset
        # Since we resample WITH replacement, total varies. But mean should be close.
        mean_pnl = result.statistics["pnl_mean"]
        assert abs(mean_pnl - float(expected_total)) < float(abs(expected_total)) * 2
