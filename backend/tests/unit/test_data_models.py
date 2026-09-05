import pytest
from datetime import datetime
from data.models import Candle, Tick, Quote, Timeframe


def test_candle_creation():
    candle = Candle(
        symbol="AAPL", timeframe=Timeframe.ONE_HOUR,
        open=150.0, high=151.0, low=149.5, close=150.5,
        volume=10000, timestamp=datetime.utcnow()
    )
    assert candle.symbol == "AAPL"
    assert candle.close == 150.5
    assert candle.high >= candle.low


def test_tick_creation():
    tick = Tick(symbol="AAPL", price=150.5, size=100, timestamp=datetime.utcnow(), exchange="NYSE")
    assert tick.price == 150.5


def test_quote_creation():
    quote = Quote(symbol="EURUSD", bid=1.0890, ask=1.0892, bid_size=1000000, ask_size=1000000, timestamp=datetime.utcnow())
    assert quote.bid < quote.ask
    assert quote.spread == pytest.approx(0.0002)


def test_timeframe_enum():
    assert Timeframe.ONE_MINUTE.value == "1M"
    assert Timeframe.ONE_HOUR.value == "1H"
    assert Timeframe.ONE_DAY.value == "1D"


def test_candle_to_dict():
    candle = Candle("AAPL", Timeframe.ONE_HOUR, 150.0, 151.0, 149.5, 150.5, 10000, datetime.utcnow())
    d = candle.to_dict()
    assert d["symbol"] == "AAPL"
    assert d["close"] == 150.5


def test_candle_validation():
    with pytest.raises(ValueError):
        Candle("X", Timeframe.ONE_HOUR, 100, 90, 110, 105, 1000, datetime.utcnow())
