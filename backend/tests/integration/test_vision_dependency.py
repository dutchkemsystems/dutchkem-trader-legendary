from api.deps import get_chart_analyzer, get_consensus_engine


def test_chart_analyzer_singleton():
    a1 = get_chart_analyzer()
    a2 = get_chart_analyzer()
    assert a1 is a2  # Same instance


def test_consensus_engine_has_technical_analyst():
    engine = get_consensus_engine()
    # Check that technical analyst has chart_analyzer
    tech = [a for a in engine.analysts if hasattr(a, 'chart_analyzer')]
    assert len(tech) > 0
