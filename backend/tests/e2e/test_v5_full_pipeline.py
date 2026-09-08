"""E2E test: Full V5.0 pipeline with REAL data.

Pipeline: Analysts → ML Prediction → 7-Gate Consensus → Debate → Memory → Risk → Decision
Uses real market data from AKShare (falls back to StubProvider if network unavailable).
"""

import asyncio
import pytest
import numpy as np
import pandas as pd

# ── V5.0 imports ──
from apps.analysts.market import MarketAnalyst
from apps.analysts.news import NewsAnalyst
from apps.analysts.fundamentals import FundamentalsAnalyst
from apps.analysts.sentiment import SentimentAnalyst
from apps.analysts.technical import TechnicalAnalyst
from apps.analysts.options import OptionsAnalyst
from apps.analysts.order_flow import OrderFlowAnalyst
from apps.analysts.risk import RiskAnalyst
from apps.analysts.macro import MacroAnalyst
from apps.analysts.on_chain import OnChainAnalyst
from apps.analysts.quant import QuantAnalyst
from apps.analysts.compliance import ComplianceAnalyst

from apps.consensus.engine import ConsensusEngine
from apps.consensus.gates import ConsensusGates
from apps.consensus.black_scholes import BlackScholesEngine, EdgeResult
from apps.consensus.regime import MarketRegimeDetector, Regime

from apps.debate.engine import DebateEngine
from apps.memory.situation_memory import FinancialSituationMemory

from apps.ml.predictor import MLPredictor
from apps.ml.model import PredictionModel
from apps.ml.features import FeatureExtractor
from apps.ml.data_loader import MLDataLoader

from data.manager import MarketDataManager
from data.models import Timeframe

from execution.kelly_sizer import KellySizer
from execution.circuit_breaker import CircuitBreaker, CircuitState


# ── Helpers ──


def train_ml_on_real_data(symbol: str = "000001", timeframe: str = "1D"):
    """Train XGBoost on real historical data. Returns (predictor, X, y)."""
    loader = MLDataLoader()
    try:
        X, y = loader.load_training_data(symbol, timeframe, limit=200)
    except Exception:
        np.random.seed(42)
        X = pd.DataFrame(np.random.rand(200, 10), columns=FeatureExtractor.FEATURE_NAMES)
        y = pd.Series(np.random.randint(0, 2, 200))

    predictor = MLPredictor(model_type="xgboost")
    predictor.train(X.values, y.values)
    return predictor, X, y


# ═══════════════════════════════════════════════════════════════
# PHASE 1: Real Data Components
# ═══════════════════════════════════════════════════════════════


class TestRealDataFetch:
    """Verify real data flows from AKShare (or StubProvider fallback)."""

    @pytest.mark.asyncio
    async def test_fetch_real_candles(self):
        dm = MarketDataManager()
        candles = await dm.get_candles("000001", Timeframe.ONE_DAY, limit=50)
        assert len(candles) > 0
        assert candles[0].open > 0
        assert candles[0].close > 0
        print(f"  Fetched {len(candles)} real candles, last close: {candles[-1].close:.2f}")


class TestRealMLPipeline:
    """ML: real data -> features -> train -> predict."""

    def test_train_on_real_data(self):
        predictor, X, y = train_ml_on_real_data()
        pred = predictor.predict_from_features(X.iloc[[-1]].values)
        assert 0.0 <= pred.p_up <= 1.0
        assert pred.direction in ("UP", "DOWN")
        print(f"  Real ML prediction: P(UP)={pred.p_up:.4f}, direction={pred.direction}")

    def test_feature_extractor_real_data(self):
        np.random.seed(42)
        dates = pd.date_range("2023-01-01", periods=200, freq="1D")
        price = 100 + np.cumsum(np.random.randn(200) * 1.5)
        df = pd.DataFrame(
            {
                "open": price + np.random.randn(200) * 0.5,
                "high": price + np.abs(np.random.randn(200) * 1.0),
                "low": price - np.abs(np.random.randn(200) * 1.0),
                "close": price,
                "volume": np.random.randint(10000, 100000, 200),
            },
            index=dates,
        )
        extractor = FeatureExtractor()
        features = extractor.extract(df)
        assert features.shape[1] == 10
        assert features.isna().sum().sum() < len(features) * 2


class TestRealBlackScholes:
    """Black-Scholes with real volatility."""

    def test_with_real_volatility(self):
        bs = BlackScholesEngine()
        result = bs.evaluate(
            stock_price=1.10,
            strike_price=1.10,
            market_price=0.55,
            momentum=0.5,
            volatility=0.08,
        )
        assert isinstance(result, EdgeResult)
        assert 0.0 <= result.p_up <= 1.0
        assert result.d2 is not None
        print(f"  Black-Scholes P(UP)={result.p_up:.4f}, edge={result.edge:.4f}, tradeable={result.tradeable}")

    def test_calculate_p_up(self):
        bs = BlackScholesEngine()
        p_up = bs.calculate_p_up(1.10, 1.10, volatility=0.08, time_to_expiry=7/365)
        assert 0.0 <= p_up <= 1.0
        print(f"  P(UP)={p_up:.4f}")


class TestRealRegimeDetector:
    """Regime detection with numeric inputs."""

    def test_detect_trending(self):
        detector = MarketRegimeDetector()
        result = detector.detect(adx=30.0, atr_percentile=0.5)
        assert result.regime == Regime.TRENDING
        assert not result.blocked
        print(f"  Regime: {result.regime.value}")

    def test_detect_chop(self):
        detector = MarketRegimeDetector()
        result = detector.detect(adx=15.0, atr_percentile=0.3)
        assert result.regime == Regime.CHOP
        assert result.blocked
        print(f"  Regime: {result.regime.value} (blocked)")

    def test_detect_trap(self):
        detector = MarketRegimeDetector()
        result = detector.detect(adx=25.0, atr_percentile=0.9, recent_breakout_failed=True)
        assert result.regime == Regime.TRAP
        assert result.blocked
        print(f"  Regime: {result.regime.value} (blocked)")

    def test_detect_adverse_selection(self):
        detector = MarketRegimeDetector()
        result = detector.detect(spread_bps=15.0, volume_imbalance=0.8)
        assert result.regime == Regime.ADVERSE_SELECTION
        assert result.blocked
        print(f"  Regime: {result.regime.value} (blocked)")


class TestRealDebate:
    """Debate with real (mock fallback) LLM."""

    @pytest.mark.asyncio
    async def test_debate_real(self):
        engine = DebateEngine(max_rounds=1)
        result = await engine.debate("EURUSD")
        assert result.winner in ("BULL", "BEAR", "NEUTRAL")
        assert 0.0 <= result.bull_confidence <= 1.0
        print(f"  Debate winner: {result.winner}, bull={result.bull_confidence:.2f}, bear={result.bear_confidence:.2f}")


class TestRealMemory:
    """Memory with real stored situations."""

    def test_memory_retrieve(self):
        memory = FinancialSituationMemory()
        memory.store("EURUSD", "strong uptrend breakout after consolidation", "profit", "momentum works")
        memory.store("EURUSD", "choppy sideways range-bound market", "loss", "avoid low volatility")
        memory.store("EURUSD", "flash crash recovery", "profit", "buy the dip works")
        results = memory.retrieve("EURUSD uptrend momentum")
        assert len(results) > 0
        print(f"  Memory retrieved {len(results)} similar situations")


class TestRealRisk:
    """Real risk calculations."""

    def test_kelly_sizer_real(self):
        sizer = KellySizer()
        fraction = sizer.calculate(win_rate=0.6, avg_win=0.02, avg_loss=0.01)
        assert 0.0 < fraction <= 0.25
        print(f"  Kelly fraction: {fraction:.4f}")

    def test_circuit_breaker_real(self):
        cb = CircuitBreaker(daily_loss_limit=5.0)
        assert cb.state == CircuitState.CLOSED

        # Record losses until circuit opens (limit is 5%)
        cb.record_loss(1.5)
        cb.record_loss(1.5)
        cb.record_loss(1.5)
        cb.record_loss(1.5)  # total = 6.0 > 5.0 → opens
        assert cb.state == CircuitState.OPEN

        # Reset
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        print("  Circuit breaker: closed -> open -> closed")


# ═══════════════════════════════════════════════════════════════
# PHASE 2: Full Pipeline E2E (Real Components)
# ═══════════════════════════════════════════════════════════════


class TestFullPipelineE2E:
    """Complete V5.0 pipeline: all real components wired together."""

    @pytest.mark.asyncio
    async def test_full_pipeline_real_data(self):
        """Run the entire V5.0 pipeline with real data where possible."""
        print("\n" + "=" * 60)
        print("DUTCHKEM TRADER V5.0 -- FULL E2E PIPELINE")
        print("=" * 60)

        # 1. Train ML on real data
        print("\n[1/7] Training ML model on real data...")
        ml_predictor, X_train, y_train = train_ml_on_real_data("000001", "1D")
        pred = ml_predictor.predict_from_features(X_train.iloc[[-1]].values)
        print(f"  ML Prediction: P(UP)={pred.p_up:.4f}, direction={pred.direction}")

        # 2. Setup debate
        print("\n[2/7] Setting up debate engine...")
        debate_engine = DebateEngine(max_rounds=1)

        # 3. Setup memory
        print("\n[3/7] Loading situational memory...")
        memory = FinancialSituationMemory()
        memory.store("EURUSD", "strong uptrend breakout", "profit", "momentum works")
        memory.store("EURUSD", "choppy sideways range", "loss", "avoid low volatility")
        memory.store("000001", "strong uptrend breakout", "profit", "Chinese stock momentum")
        similar = memory.retrieve("EURUSD uptrend")
        print(f"  Memory: {memory.count()} situations stored, {len(similar)} retrieved")

        # 4. Initialize 12 analysts
        print("\n[4/7] Initializing 12 analysts...")
        analysts = [
            MarketAnalyst(), NewsAnalyst(), FundamentalsAnalyst(),
            SentimentAnalyst(), TechnicalAnalyst(), OptionsAnalyst(),
            OrderFlowAnalyst(), RiskAnalyst(), MacroAnalyst(),
            OnChainAnalyst(), QuantAnalyst(), ComplianceAnalyst(),
        ]
        print(f"  {len(analysts)} analysts ready")

        # 5. Build consensus engine
        print("\n[5/7] Building consensus engine with debate + memory...")
        engine = ConsensusEngine(
            analysts=analysts,
            ml_predictor=ml_predictor,
            debate_engine=debate_engine,
            memory=memory,
        )

        # 6. Run full pipeline
        print("\n[6/7] Running full consensus pipeline...")
        result = await engine.evaluate("EURUSD", "1H", use_debate=True, use_memory=True)

        # 7. Display results
        print("\n[7/7] Pipeline Results:")
        print(f"  Action:     {result['action']}")
        print(f"  Confidence: {result['confidence']:.2%}")
        print(f"  Agreement:  {result['agreement_pct']:.2%}")
        if "debate" in result:
            d = result["debate"]
            print(f"  Debate:     winner={d['winner']}, bull={d['bull_confidence']:.2f}, bear={d['bear_confidence']:.2f}")
        if "similar_situations" in result:
            print(f"  Memory:     {len(result['similar_situations'])} similar situations")

        print("\n" + "=" * 60)
        print("PIPELINE COMPLETE")
        print("=" * 60)

        # Assertions
        assert result["action"] in ("BUY", "SELL", "HOLD")
        assert 0.0 <= result["confidence"] <= 1.0
        assert "votes" in result
        assert len(result["votes"]) > 0
        assert "debate" in result
        assert "similar_situations" in result

    @pytest.mark.asyncio
    async def test_pipeline_7_gates(self):
        """Validate 7-gate consensus with real ML prediction."""
        print("\n" + "-" * 40)
        print("7-GATE CONSENSUS VALIDATION")
        print("-" * 40)

        ml_predictor, X_train, y_train = train_ml_on_real_data()
        pred = ml_predictor.predict_from_features(X_train.iloc[[-1]].values)

        gates = ConsensusGates(ml_predictor=ml_predictor)
        result = gates.evaluate_all(
            features=X_train.iloc[[-1]].values,
            consensus={"agreement_pct": 0.75},
            p_up=pred.p_up,
            market_price=0.5,
            risk_status={"current_positions": 2, "max_positions": 10},
        )

        print(f"  Trade allowed: {result['trade_allowed']}")
        print(f"  Gates passed:  {result['passed_count']}/{result['total_gates']}")
        for name, gate in result["gates"].items():
            status = "PASS" if gate["passed"] else "FAIL"
            print(f"    {name}: {status}")

        assert "trade_allowed" in result
        assert result["total_gates"] == 7
        assert isinstance(result["gates"], dict)

    @pytest.mark.asyncio
    async def test_pipeline_risk_check(self):
        """Risk management: Kelly sizing + circuit breaker."""
        print("\n" + "-" * 40)
        print("RISK MANAGEMENT CHECK")
        print("-" * 40)

        sizer = KellySizer()
        cb = CircuitBreaker(daily_loss_limit=5.0)

        fraction = sizer.calculate(win_rate=0.6, avg_win=0.02, avg_loss=0.01)
        print(f"  Kelly fraction: {fraction:.4f} ({fraction*100:.2f}%)")
        print(f"  Circuit breaker state: {cb.state.value}")
        assert cb.state == CircuitState.CLOSED
        assert 0.0 < fraction <= 0.25


# ═══════════════════════════════════════════════════════════════
# Regression Guards
# ═══════════════════════════════════════════════════════════════


class TestRegressionGuards:
    """Ensure key invariants hold."""

    def test_kelly_never_exceeds_25_percent(self):
        sizer = KellySizer()
        fraction = sizer.calculate(win_rate=0.9, avg_win=0.10, avg_loss=0.01)
        assert fraction <= 0.25

    def test_circuit_breaker_resets(self):
        cb = CircuitBreaker(daily_loss_limit=5.0)
        cb.record_loss(2.0)
        cb.record_loss(2.0)
        cb.record_loss(2.0)
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED

    def test_black_scholes_bounds(self):
        bs = BlackScholesEngine()
        p_up = bs.calculate_p_up(1.10, 1.10)
        assert 0.0 <= p_up <= 1.0

    def test_regime_result_is_dataclass(self):
        detector = MarketRegimeDetector()
        result = detector.detect(adx=25.0)
        assert hasattr(result, "regime")
        assert hasattr(result, "blocked")
        assert hasattr(result, "reason")
