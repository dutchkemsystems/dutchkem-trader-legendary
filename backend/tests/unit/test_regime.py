import pytest
from apps.consensus.regime import MarketRegimeDetector, Regime, RegimeResult


def test_detect_chop():
    detector = MarketRegimeDetector()
    result = detector.detect(adx=15.0, atr_percentile=0.5, price_range_pct=0.002)
    assert result.regime == Regime.CHOP
    assert result.blocked is True


def test_detect_trending():
    detector = MarketRegimeDetector()
    result = detector.detect(adx=35.0, atr_percentile=0.7, price_range_pct=0.01)
    assert result.regime == Regime.TRENDING
    assert result.blocked is False


def test_detect_trap():
    detector = MarketRegimeDetector()
    result = detector.detect(
        adx=30.0,
        atr_percentile=0.9,
        price_range_pct=0.001,
        recent_breakout_failed=True,
    )
    assert result.regime == Regime.TRAP
    assert result.blocked is True


def test_detect_adverse_selection():
    detector = MarketRegimeDetector()
    result = detector.detect(
        adx=25.0,
        spread_bps=15.0,
        volume_imbalance=0.8,
        slippage_bps=8.0,
    )
    assert result.regime == Regime.ADVERSE_SELECTION
    assert result.blocked is True


def test_detect_normal():
    detector = MarketRegimeDetector()
    result = detector.detect(adx=22.0, atr_percentile=0.5, price_range_pct=0.005)
    assert result.regime == Regime.NORMAL
    assert result.blocked is False


def test_result_has_reason_and_confidence():
    detector = MarketRegimeDetector()
    result = detector.detect(adx=15.0)
    assert isinstance(result.reason, str)
    assert len(result.reason) > 0
    assert 0.0 <= result.confidence <= 1.0


def test_adverse_selection_priority_over_trap():
    """Adverse selection should be detected before trap even when both conditions met."""
    detector = MarketRegimeDetector()
    result = detector.detect(
        adx=25.0,
        atr_percentile=0.9,
        spread_bps=15.0,
        volume_imbalance=0.8,
        recent_breakout_failed=True,
    )
    assert result.regime == Regime.ADVERSE_SELECTION
    assert result.blocked is True


def test_trap_priority_over_chop():
    """Trap should be detected before chop when both conditions met."""
    detector = MarketRegimeDetector()
    result = detector.detect(
        adx=15.0,
        atr_percentile=0.9,
        recent_breakout_failed=True,
    )
    assert result.regime == Regime.TRAP
    assert result.blocked is True


def test_edge_case_adx_boundary_chop():
    """ADX exactly at chop threshold (20) should NOT be chop (it's >= 20)."""
    detector = MarketRegimeDetector()
    result = detector.detect(adx=20.0, atr_percentile=0.5)
    assert result.regime != Regime.CHOP


def test_edge_case_adx_boundary_trend():
    """ADX exactly at trend threshold (25) should be trend (it's >= 25)."""
    detector = MarketRegimeDetector()
    result = detector.detect(adx=25.0, atr_percentile=0.5)
    assert result.regime == Regime.TRENDING
    assert result.blocked is False


def test_defaults_produce_trending():
    """Default adx=25.0 meets trend threshold, so defaults produce TRENDING."""
    detector = MarketRegimeDetector()
    result = detector.detect()
    assert result.regime == Regime.TRENDING
    assert result.blocked is False
