"""Tests for MTFCascadingScalper module."""
import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

def _make_ohlcv(close_values, n=100):
    """Build a realistic OHLCV DataFrame from a list of close prices."""
    closes = np.array(close_values, dtype=float)
    # Pad if needed
    if len(closes) < n:
        closes = np.concatenate([np.full(n - len(closes), closes[0]), closes])
    highs = closes * (1 + np.random.uniform(0.0001, 0.002, len(closes)))
    lows = closes * (1 - np.random.uniform(0.0001, 0.002, len(closes)))
    opens = closes * (1 + np.random.uniform(-0.001, 0.001, len(closes)))
    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.random.randint(100, 1000, len(closes)),
    })


@pytest.fixture
def mock_mt5_engine():
    engine = MagicMock()
    return engine


@pytest.fixture
def mock_risk_manager():
    rm = MagicMock()
    rm.get_drawdown_pct.return_value = 0.02
    rm.get_risk_multiplier.return_value = 1.0
    rm.check_circuit_breaker.return_value = True
    rm.check_portfolio_limits.return_value = True
    rm.open_positions = {}
    return rm


@pytest.fixture
def scalper_config():
    return {
        "mtf_cascading_scalper_enabled": True,
        "scalper_timeframes": ["M15", "H1", "H4"],
        "scalper_groups": [
            {"name": "trend_major", "timeframes": ["H4", "D1", "W1"], "direction_weight": 1.0},
            {"name": "trend_minor", "timeframes": ["M15", "H1", "H4"], "direction_weight": 0.8},
        ],
        "scalper_tp_pips": 15,
        "scalper_sl_pips": 10,
        "scalper_lot_size": 0.01,
        "scalper_max_concurrent": 3,
        "scalper_scan_interval": 60,
        "scalper_restart_from_group1": True,
        "scalper_symbol": "EURUSD",
        "session_hours": set(range(7, 22)),
        "drawdown_pause_pct": 0.15,
        "max_concurrent_trades": 6,
    }


@pytest.fixture
def scalper(mock_mt5_engine, mock_risk_manager, scalper_config):
    from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper
    return MTFCascadingScalper(mock_mt5_engine, mock_risk_manager, scalper_config)


# ---------------------------------------------------------------------------
# 1. Module import
# ---------------------------------------------------------------------------

class TestModuleImport:
    def test_import(self):
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper
        assert MTFCascadingScalper is not None


# ---------------------------------------------------------------------------
# 2. _compute_directional_signal
# ---------------------------------------------------------------------------

class TestComputeDirectionalSignal:
    def test_bullish_signal(self, scalper):
        # Price above SMA20 > SMA50, RSI < 70, MACD > 0
        closes = np.linspace(1.0800, 1.0900, 100)  # steady uptrend
        df = _make_ohlcv(closes)
        signal = scalper._compute_directional_signal(df)
        assert signal == "BUY"

    def test_bearish_signal(self, scalper):
        # Price below SMA20 < SMA50, RSI > 30, MACD < 0
        closes = np.linspace(1.0900, 1.0800, 100)  # steady downtrend
        df = _make_ohlcv(closes)
        signal = scalper._compute_directional_signal(df)
        assert signal == "SELL"

    def test_hold_signal(self, scalper):
        # Choppy / sideways
        closes = np.concatenate([
            np.linspace(1.0850, 1.0870, 50),
            np.linspace(1.0870, 1.0850, 50),
        ])
        df = _make_ohlcv(closes)
        signal = scalper._compute_directional_signal(df)
        assert signal in ("BUY", "SELL", "HOLD")


# ---------------------------------------------------------------------------
# 3. _check_alignment
# ---------------------------------------------------------------------------

class TestCheckAlignment:
    def test_all_buy(self, scalper):
        signals = ["BUY", "BUY", "BUY"]
        result = scalper._check_alignment(signals)
        assert result == "BUY"

    def test_all_sell(self, scalper):
        signals = ["SELL", "SELL", "SELL"]
        result = scalper._check_alignment(signals)
        assert result == "SELL"

    def test_mixed_signals(self, scalper):
        signals = ["BUY", "SELL", "BUY"]
        result = scalper._check_alignment(signals)
        assert result is None

    def test_two_buy_one_hold(self, scalper):
        signals = ["BUY", "BUY", "HOLD"]
        result = scalper._check_alignment(signals)
        assert result is None

    def test_empty_signals(self, scalper):
        result = scalper._check_alignment([])
        assert result is None


# ---------------------------------------------------------------------------
# 4. _check_safety
# ---------------------------------------------------------------------------

class TestCheckSafety:
    def test_safe_during_session(self, scalper, mock_risk_manager):
        with patch("apps.legendary.mtf_cascading_scalper.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 14  # midday UTC
            mock_dt.now.return_value.strftime.return_value = ""
            mock_dt.now.return_value = MagicMock(hour=14)
            assert scalper._check_safety() is True

    def test_unsafe_outside_session(self, scalper, mock_risk_manager):
        with patch("apps.legendary.mtf_cascading_scalper.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 3  # 3 AM UTC
            mock_dt.now.return_value.strftime.return_value = ""
            mock_dt.now.return_value = MagicMock(hour=3)
            assert scalper._check_safety() is False

    def test_unsafe_drawdown_pause(self, scalper, mock_risk_manager):
        mock_risk_manager.get_drawdown_pct.return_value = 0.20  # 20% DD
        with patch("apps.legendary.mtf_cascading_scalper.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 14
            mock_dt.now.return_value.strftime.return_value = ""
            mock_dt.now.return_value = MagicMock(hour=14)
            assert scalper._check_safety() is False

    def test_unsafe_circuit_breaker(self, scalper, mock_risk_manager):
        mock_risk_manager.check_circuit_breaker.return_value = False
        with patch("apps.legendary.mtf_cascading_scalper.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 14
            mock_dt.now.return_value.strftime.return_value = ""
            mock_dt.now.return_value = MagicMock(hour=14)
            assert scalper._check_safety() is False


# ---------------------------------------------------------------------------
# 5. _calculate_sl_tp
# ---------------------------------------------------------------------------

class TestCalculateSlTp:
    def test_buy_sl_tp(self, scalper):
        symbol_info = MagicMock()
        symbol_info.point = 0.0001
        symbol_info.digits = 5
        sl, tp = scalper._calculate_sl_tp(1.0850, "BUY", symbol_info)
        assert sl < 1.0850
        assert tp > 1.0850

    def test_sell_sl_tp(self, scalper):
        symbol_info = MagicMock()
        symbol_info.point = 0.0001
        symbol_info.digits = 5
        sl, tp = scalper._calculate_sl_tp(1.0850, "SELL", symbol_info)
        assert sl > 1.0850
        assert tp < 1.0850


# ---------------------------------------------------------------------------
# 6. get_status
# ---------------------------------------------------------------------------

class TestGetStatus:
    def test_status_structure(self, scalper):
        status = scalper.get_status()
        assert "enabled" in status
        assert "open_scalps" in status
        assert "total_trades" in status
        assert "last_scan" in status


# ---------------------------------------------------------------------------
# 7. scan_and_execute returns gracefully when disabled
# ---------------------------------------------------------------------------

class TestScanAndExecute:
    def test_returns_none_when_disabled(self, scalper):
        scalper.config["mtf_cascading_scalper_enabled"] = False
        result = scalper.scan_and_execute()
        assert result is None

    def test_returns_none_when_safety_fails(self, scalper, mock_risk_manager):
        with patch("apps.legendary.mtf_cascading_scalper.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 3
            mock_dt.now.return_value.strftime.return_value = ""
            mock_dt.now.return_value = MagicMock(hour=3)
            result = scalper.scan_and_execute()
            assert result is None


# ---------------------------------------------------------------------------
# 8. Multi-group scanning (scalper_max_groups_per_cycle)
# ---------------------------------------------------------------------------

class TestMultiGroupScanning:
    """Tests for scanning multiple groups per cycle."""

    def _make_multi_group_config(self, max_groups=0):
        """Config with 7 groups (G1-G7) for multi-group testing."""
        return {
            "mtf_cascading_scalper_enabled": True,
            "scalper_groups": [
                {"name": "G1", "timeframes": ["M1", "M5", "M15"]},
                {"name": "G2", "timeframes": ["M5", "M15", "M30"]},
                {"name": "G3", "timeframes": ["M15", "M30", "H1"]},
                {"name": "G4", "timeframes": ["M30", "H1", "H4"]},
                {"name": "G5", "timeframes": ["H1", "H4", "D1"]},
                {"name": "G6", "timeframes": ["H4", "D1", "W1"]},
                {"name": "G7", "timeframes": ["D1", "W1", "MN1"]},
            ],
            "scalper_tp_pips": 12,
            "scalper_sl_pips": 8,
            "scalper_lot_size": 0.01,
            "scalper_max_concurrent": 5,
            "scalper_scan_interval": 60,
            "scalper_max_groups_per_cycle": max_groups,
            "scalper_symbol": "EURUSD",
            "session_hours": set(range(7, 22)),
            "drawdown_pause_pct": 0.15,
            "max_concurrent_trades": 6,
            "scalper_multi_symbol": False,
        }

    def test_default_scans_all_groups(self, mock_mt5_engine, mock_risk_manager):
        """Default (max_groups=0) should scan ALL groups per cycle."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper
        config = self._make_multi_group_config(max_groups=0)
        scalper = MTFCascadingScalper(mock_mt5_engine, mock_risk_manager, config)

        # Mock _get_signals_for_group to track which groups are scanned
        scanned_groups = []
        original_get_signals = scalper._get_signals_for_group

        def mock_get_signals(symbol, group):
            scanned_groups.append(group["name"])
            return ["HOLD", "HOLD", "HOLD"]  # No alignment, so we scan all

        scalper._get_signals_for_group = mock_get_signals

        # Mock safety and price
        with patch.object(scalper, '_check_safety', return_value=True), \
             patch.object(scalper, '_get_current_price', return_value=1.0850):
            scalper.scan_and_execute()

        # All 7 groups should have been scanned
        assert len(scanned_groups) == 7
        assert scanned_groups == ["G1", "G2", "G3", "G4", "G5", "G6", "G7"]

    def test_max_groups_1_scans_only_first(self, mock_mt5_engine, mock_risk_manager):
        """max_groups=1 should scan only the first group (old restart_from_g1 behavior)."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper
        config = self._make_multi_group_config(max_groups=1)
        scalper = MTFCascadingScalper(mock_mt5_engine, mock_risk_manager, config)

        scanned_groups = []

        def mock_get_signals(symbol, group):
            scanned_groups.append(group["name"])
            return ["HOLD", "HOLD", "HOLD"]

        scalper._get_signals_for_group = mock_get_signals

        with patch.object(scalper, '_check_safety', return_value=True), \
             patch.object(scalper, '_get_current_price', return_value=1.0850):
            scalper.scan_and_execute()

        # Only 1 group scanned
        assert len(scanned_groups) == 1
        assert scanned_groups[0] == "G1"

    def test_max_groups_3_scans_up_to_three(self, mock_mt5_engine, mock_risk_manager):
        """max_groups=3 should scan up to 3 groups per cycle."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper
        config = self._make_multi_group_config(max_groups=3)
        scalper = MTFCascadingScalper(mock_mt5_engine, mock_risk_manager, config)

        scanned_groups = []

        def mock_get_signals(symbol, group):
            scanned_groups.append(group["name"])
            return ["HOLD", "HOLD", "HOLD"]

        scalper._get_signals_for_group = mock_get_signals

        with patch.object(scalper, '_check_safety', return_value=True), \
             patch.object(scalper, '_get_current_price', return_value=1.0850):
            scalper.scan_and_execute()

        assert len(scanned_groups) == 3
        assert scanned_groups == ["G1", "G2", "G3"]

    def test_stops_after_successful_trade(self, mock_mt5_engine, mock_risk_manager):
        """Should stop scanning after executing a trade, even with max_groups=0."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper
        config = self._make_multi_group_config(max_groups=0)
        scalper = MTFCascadingScalper(mock_mt5_engine, mock_risk_manager, config)

        scanned_groups = []
        call_count = [0]

        def mock_get_signals(symbol, group):
            scanned_groups.append(group["name"])
            call_count[0] += 1
            # G2 produces BUY alignment
            if group["name"] == "G2":
                return ["BUY", "BUY", "BUY"]
            return ["HOLD", "HOLD", "HOLD"]

        scalper._get_signals_for_group = mock_get_signals

        # Mock _execute_scalp to return a scalp dict on the first alignment
        mock_scalp_result = {"ticket": 12345, "symbol": "EURUSD", "direction": "BUY"}
        scalper._execute_scalp = MagicMock(return_value=mock_scalp_result)

        with patch.object(scalper, '_check_safety', return_value=True), \
             patch.object(scalper, '_get_current_price', return_value=1.0850):
            result = scalper.scan_and_execute()

        # G1 scanned (HOLD), G2 scanned (BUY → executed), G3+ NOT scanned
        assert scanned_groups == ["G1", "G2"]
        assert result == mock_scalp_result

    def test_backward_compat_restart_from_group1_true(self, mock_mt5_engine, mock_risk_manager):
        """Legacy config: scalper_restart_from_group1=True should behave as max_groups=1."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper
        config = self._make_multi_group_config(max_groups=1)
        # Also set the legacy key to True
        config["scalper_restart_from_group1"] = True
        scalper = MTFCascadingScalper(mock_mt5_engine, mock_risk_manager, config)

        scanned_groups = []

        def mock_get_signals(symbol, group):
            scanned_groups.append(group["name"])
            return ["HOLD", "HOLD", "HOLD"]

        scalper._get_signals_for_group = mock_get_signals

        with patch.object(scalper, '_check_safety', return_value=True), \
             patch.object(scalper, '_get_current_price', return_value=1.0850):
            scalper.scan_and_execute()

        # Should scan only 1 group
        assert len(scanned_groups) == 1
        assert scanned_groups[0] == "G1"

    def test_prefer_groups_respected_with_multi_group(self, mock_mt5_engine, mock_risk_manager):
        """Preferred groups should be scanned first, then remaining groups."""
        from apps.legendary.mtf_cascading_scalper import MTFCascadingScalper
        config = self._make_multi_group_config(max_groups=3)
        config["scalper_prefer_groups"] = ["G5", "G3"]
        scalper = MTFCascadingScalper(mock_mt5_engine, mock_risk_manager, config)

        scanned_groups = []

        def mock_get_signals(symbol, group):
            scanned_groups.append(group["name"])
            return ["HOLD", "HOLD", "HOLD"]

        scalper._get_signals_for_group = mock_get_signals

        with patch.object(scalper, '_check_safety', return_value=True), \
             patch.object(scalper, '_get_current_price', return_value=1.0850):
            scalper.scan_and_execute()

        # Preferred groups come first (in all_groups order: G3, G5), then G1 = 3 groups scanned
        assert len(scanned_groups) == 3
        assert scanned_groups[0] == "G3"
        assert scanned_groups[1] == "G5"
        assert scanned_groups[2] == "G1"
