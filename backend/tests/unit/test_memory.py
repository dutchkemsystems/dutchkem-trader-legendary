import pytest
from apps.memory.situation_memory import FinancialSituationMemory
from apps.memory.summariser import SituationSummariser
from apps.memory.bm25_retriever import BM25Retriever


def test_store_situation():
    memory = FinancialSituationMemory()
    memory.store(
        "EURUSD",
        "Strong uptrend with high volume",
        "BUY at 1.0950, +50 pips",
        "Volume confirmation helps",
    )
    assert memory.count() == 1


def test_retrieve_similar():
    memory = FinancialSituationMemory()
    memory.store("EURUSD", "Strong uptrend with high volume", "profit", "volume confirms")
    memory.store("EURUSD", "Choppy sideways market", "loss", "avoid chop")
    memory.store("GBPUSD", "Bearish breakdown", "profit", "breakouts work")
    results = memory.retrieve("uptrend volume", top_k=2)
    assert len(results) <= 2
    assert results[0].relevance_score >= 0


def test_bm25_retriever():
    retriever = BM25Retriever()
    retriever.add_documents(["bullish trend", "bearish reversal", "sideways chop"])
    results = retriever.search("bullish", top_k=1)
    assert len(results) == 1
    assert results[0][0] == 0  # First doc matches


def test_summarise():
    summariser = SituationSummariser()
    long_text = "word " * 500
    summary = summariser.summarise(long_text)
    assert len(summary.split()) <= 401
