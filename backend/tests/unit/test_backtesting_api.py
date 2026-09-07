"""Tests for backtesting API endpoints."""
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_candles():
    """Generate sample OHLCV candle data for backtesting."""
    candles = []
    base_price = 1.1000
    for i in range(50):
        open_p = base_price + (i % 10) * 0.0001
        high_p = open_p + 0.0020
        low_p = open_p - 0.0020
        close_p = open_p + 0.0010
        candles.append({
            "symbol": "EURUSD",
            "timeframe": "1H",
            "open": round(open_p, 5),
            "high": round(high_p, 5),
            "low": round(low_p, 5),
            "close": round(close_p, 5),
            "volume": 1000,
            "timestamp": datetime(2024, 1, 1, i % 24).isoformat(),
        })
    return candles


@pytest.fixture
def sample_trades():
    """Sample trade records for Monte Carlo."""
    return [
        {
            "symbol": "EURUSD",
            "side": "BUY",
            "quantity": "0.01",
            "entry_price": "1.1000",
            "exit_price": "1.1050",
            "pnl": "50.00",
        },
        {
            "symbol": "EURUSD",
            "side": "SELL",
            "quantity": "0.01",
            "entry_price": "1.1050",
            "exit_price": "1.1020",
            "pnl": "30.00",
        },
        {
            "symbol": "EURUSD",
            "side": "BUY",
            "quantity": "0.01",
            "entry_price": "1.1020",
            "exit_price": "1.0980",
            "pnl": "-40.00",
        },
    ]


# ---------------------------------------------------------------------------
# POST /api/v1/backtest/run
# ---------------------------------------------------------------------------

class TestBacktestRun:
    def test_run_returns_200(self, client, sample_candles):
        payload = {
            "symbol": "EURUSD",
            "timeframe": "1H",
            "initial_balance": 10000,
            "risk_per_trade": 0.01,
            "stop_loss_pips": 50,
            "take_profit_pips": 100,
            "contract_size": 100000,
            "candles": sample_candles,
        }
        response = client.post("/api/v1/backtest/run", json=payload)
        assert response.status_code == 200

    def test_run_result_has_required_fields(self, client, sample_candles):
        payload = {
            "symbol": "EURUSD",
            "timeframe": "1H",
            "initial_balance": 10000,
            "risk_per_trade": 0.01,
            "stop_loss_pips": 50,
            "take_profit_pips": 100,
            "contract_size": 100000,
            "candles": sample_candles,
        }
        response = client.post("/api/v1/backtest/run", json=payload)
        data = response.json()
        assert "symbol" in data
        assert "total_trades" in data
        assert "win_rate" in data
        assert "total_pnl" in data
        assert "profit_factor" in data
        assert "sharpe_ratio" in data
        assert "max_drawdown_pct" in data
        assert "equity_history" in data
        assert "trade_history" in data
        assert "metrics_summary" in data

    def test_run_empty_candles(self, client):
        payload = {
            "symbol": "EURUSD",
            "timeframe": "1H",
            "initial_balance": 10000,
            "candles": [],
        }
        response = client.post("/api/v1/backtest/run", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_trades"] == 0
        assert data["equity_history"] == [10000.0]

    def test_run_with_custom_params(self, client, sample_candles):
        payload = {
            "symbol": "GBPUSD",
            "timeframe": "4H",
            "initial_balance": 50000,
            "risk_per_trade": 0.02,
            "stop_loss_pips": 30,
            "take_profit_pips": 60,
            "contract_size": 100000,
            "candles": sample_candles,
        }
        response = client.post("/api/v1/backtest/run", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "GBPUSD"

    def test_run_missing_symbol_returns_422(self, client, sample_candles):
        payload = {
            "timeframe": "1H",
            "initial_balance": 10000,
            "candles": sample_candles,
        }
        response = client.post("/api/v1/backtest/run", json=payload)
        assert response.status_code == 422

    def test_run_missing_candles_returns_422(self, client):
        payload = {
            "symbol": "EURUSD",
            "timeframe": "1H",
        }
        response = client.post("/api/v1/backtest/run", json=payload)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/backtest/walk-forward
# ---------------------------------------------------------------------------

class TestBacktestWalkForward:
    def test_walk_forward_returns_200(self, client, sample_candles):
        payload = {
            "symbol": "EURUSD",
            "timeframe": "1H",
            "initial_balance": 10000,
            "in_sample_pct": 0.7,
            "n_splits": 3,
            "risk_per_trade": 0.01,
            "stop_loss_pips": 50,
            "take_profit_pips": 100,
            "contract_size": 100000,
            "candles": sample_candles,
        }
        response = client.post("/api/v1/backtest/walk-forward", json=payload)
        assert response.status_code == 200

    def test_walk_forward_result_fields(self, client, sample_candles):
        payload = {
            "symbol": "EURUSD",
            "timeframe": "1H",
            "initial_balance": 10000,
            "in_sample_pct": 0.7,
            "n_splits": 3,
            "candles": sample_candles,
        }
        response = client.post("/api/v1/backtest/walk-forward", json=payload)
        data = response.json()
        assert "oos_results" in data
        assert "oos_equity_curve" in data
        assert "oos_metrics" in data
        assert "best_params" in data

    def test_walk_forward_empty_candles(self, client):
        payload = {
            "symbol": "EURUSD",
            "timeframe": "1H",
            "n_splits": 3,
            "candles": [],
        }
        response = client.post("/api/v1/backtest/walk-forward", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["oos_results"] == []

    def test_walk_forward_with_param_grid(self, client, sample_candles):
        payload = {
            "symbol": "EURUSD",
            "timeframe": "1H",
            "initial_balance": 10000,
            "in_sample_pct": 0.7,
            "n_splits": 3,
            "param_grid": {
                "stop_loss_pips": [30, 50],
                "take_profit_pips": [60, 100],
            },
            "candles": sample_candles,
        }
        response = client.post("/api/v1/backtest/walk-forward", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "best_params" in data
        assert "param_scores" in data


# ---------------------------------------------------------------------------
# POST /api/v1/backtest/monte-carlo
# ---------------------------------------------------------------------------

class TestBacktestMonteCarlo:
    def test_monte_carlo_returns_200(self, client, sample_trades):
        payload = {
            "trades": sample_trades,
            "n_simulations": 100,
            "confidence_level": 0.95,
            "initial_equity": 10000,
            "seed": 42,
        }
        response = client.post("/api/v1/backtest/monte-carlo", json=payload)
        assert response.status_code == 200

    def test_monte_carlo_result_fields(self, client, sample_trades):
        payload = {
            "trades": sample_trades,
            "n_simulations": 100,
            "confidence_level": 0.95,
            "initial_equity": 10000,
            "seed": 42,
        }
        response = client.post("/api/v1/backtest/monte-carlo", json=payload)
        data = response.json()
        assert "simulated_pnl" in data
        assert "simulated_max_drawdown" in data
        assert "simulated_sharpe" in data
        assert "statistics" in data
        assert "confidence_intervals" in data

    def test_monte_carlo_simulation_count(self, client, sample_trades):
        payload = {
            "trades": sample_trades,
            "n_simulations": 50,
            "confidence_level": 0.95,
            "initial_equity": 10000,
            "seed": 42,
        }
        response = client.post("/api/v1/backtest/monte-carlo", json=payload)
        data = response.json()
        assert len(data["simulated_pnl"]) == 50

    def test_monte_carlo_empty_trades(self, client):
        payload = {
            "trades": [],
            "n_simulations": 100,
        }
        response = client.post("/api/v1/backtest/monte-carlo", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["simulated_pnl"] == []

    def test_monte_carlo_missing_trades_returns_422(self, client):
        payload = {
            "n_simulations": 100,
        }
        response = client.post("/api/v1/backtest/monte-carlo", json=payload)
        assert response.status_code == 422
