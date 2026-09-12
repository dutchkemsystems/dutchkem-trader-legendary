"""Tests for Analyst Consensus Fixes — Remove Stubs, Fix Thresholds."""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from apps.analysts.base import AnalystResult


class TestAnalystResult:
    """Test AnalystResult data_source field."""

    def test_data_source_field_exists(self):
        """AnalystResult should have a data_source field."""
        result = AnalystResult(
            analyst_name="test",
            symbol="EURUSD",
            timeframe="H1",
            signal="BUY",
            confidence=0.7,
            reasoning="test",
            data_source="mt5"
        )
        assert result.data_source == "mt5"

    def test_data_source_default_is_unknown(self):
        """AnalystResult data_source should default to 'unknown'."""
        result = AnalystResult(
            analyst_name="test",
            symbol="EURUSD",
            timeframe="H1",
            signal="HOLD",
            confidence=0.5,
            reasoning="test"
        )
        assert result.data_source == "unknown"


class TestStubAnalysts:
    """Test that stub analysts set data_source='none'."""

    def test_news_analyst_stub_has_none_source(self):
        """NewsAnalyst without API should return data_source='none'."""
        from apps.analysts.news import NewsAnalyst
        analyst = NewsAnalyst()
        result = asyncio.run(analyst.analyze("EURUSD", "H1"))
        assert result.data_source == "none"
        assert result.confidence == 0.0

    def test_sentiment_analyst_stub_has_none_source(self):
        """SentimentAnalyst without API should return data_source='none'."""
        from apps.analysts.sentiment import SentimentAnalyst
        analyst = SentimentAnalyst()
        result = asyncio.run(analyst.analyze("EURUSD", "H1"))
        assert result.data_source == "none"
        assert result.confidence == 0.0

    def test_macro_analyst_stub_has_none_source(self):
        """MacroAnalyst without API should return data_source='none'."""
        from apps.analysts.macro import MacroAnalyst
        analyst = MacroAnalyst()
        result = asyncio.run(analyst.analyze("EURUSD", "H1"))
        assert result.data_source == "none"
        assert result.confidence == 0.0

    def test_options_analyst_stub_has_none_source(self):
        """OptionsAnalyst without API should return data_source='none'."""
        from apps.analysts.options import OptionsAnalyst
        analyst = OptionsAnalyst()
        result = asyncio.run(analyst.analyze("EURUSD", "H1"))
        assert result.data_source == "none"
        assert result.confidence == 0.0

    def test_on_chain_analyst_stub_has_none_source(self):
        """OnChainAnalyst without API should return data_source='none'."""
        from apps.analysts.on_chain import OnChainAnalyst
        analyst = OnChainAnalyst()
        result = asyncio.run(analyst.analyze("EURUSD", "H1"))
        assert result.data_source == "none"
        assert result.confidence == 0.0


class TestConsensusEngine:
    """Test ConsensusEngine filters stubs."""

    def test_consensus_filters_stubs(self):
        """ConsensusEngine should filter out analysts with data_source='none'."""
        from apps.consensus.engine import ConsensusEngine

        # Create mock analysts
        real_analyst = MagicMock()
        real_analyst.analyze = AsyncMock(return_value=AnalystResult(
            analyst_name="real", symbol="EURUSD", timeframe="H1",
            signal="BUY", confidence=0.8, reasoning="real data",
            data_source="mt5"
        ))

        stub_analyst = MagicMock()
        stub_analyst.analyze = AsyncMock(return_value=AnalystResult(
            analyst_name="stub", symbol="EURUSD", timeframe="H1",
            signal="HOLD", confidence=0.0, reasoning="no data",
            data_source="none"
        ))

        engine = ConsensusEngine(analysts=[real_analyst, stub_analyst])
        result = asyncio.run(engine.evaluate("EURUSD", "H1"))

        # Should only count the real analyst
        assert result['agreement_pct'] == 1.0  # 1/1 = 100%
        assert result['action'] == 'BUY'

    def test_consensus_with_all_stubs_returns_hold(self):
        """ConsensusEngine with only stubs should return HOLD."""
        from apps.consensus.engine import ConsensusEngine

        stub = MagicMock()
        stub.analyze = AsyncMock(return_value=AnalystResult(
            analyst_name="stub", symbol="EURUSD", timeframe="H1",
            signal="HOLD", confidence=0.0, reasoning="no data",
            data_source="none"
        ))

        engine = ConsensusEngine(analysts=[stub])
        result = asyncio.run(engine.evaluate("EURUSD", "H1"))

        assert result['action'] == 'HOLD'
        assert result['agreement_pct'] == 0.0


class TestAPIDeps:
    """Test API deps excludes stub analysts."""

    def test_consensus_engine_has_7_analysts(self):
        """get_consensus_engine should have 7 real analysts, not 12."""
        from api.deps import get_consensus_engine
        # Clear lru_cache to get fresh instance
        get_consensus_engine.cache_clear()
        engine = get_consensus_engine()
        assert len(engine.analysts) == 7

    def test_no_stub_analysts_in_engine(self):
        """ConsensusEngine should not contain stub analyst classes."""
        from api.deps import get_consensus_engine
        from apps.analysts.news import NewsAnalyst
        from apps.analysts.sentiment import SentimentAnalyst
        from apps.analysts.macro import MacroAnalyst
        from apps.analysts.options import OptionsAnalyst
        from apps.analysts.on_chain import OnChainAnalyst

        get_consensus_engine.cache_clear()
        engine = get_consensus_engine()

        stub_classes = (NewsAnalyst, SentimentAnalyst, MacroAnalyst, OptionsAnalyst, OnChainAnalyst)
        for analyst in engine.analysts:
            assert not isinstance(analyst, stub_classes), \
                f"Stub analyst {type(analyst).__name__} found in engine"


class TestUnifiedEngineConsensus:
    """Test unified_engine analyst list includes OrderFlow."""

    def test_order_flow_in_analyst_list(self):
        """_run_analyst_consensus should include OrderFlowAnalyst."""
        from pathlib import Path
        engine_path = Path(__file__).parent.parent.parent / "unified_engine.py"
        content = engine_path.read_text(encoding="utf-8")
        assert '("OrderFlow", "apps.analysts.order_flow", "OrderFlowAnalyst")' in content
