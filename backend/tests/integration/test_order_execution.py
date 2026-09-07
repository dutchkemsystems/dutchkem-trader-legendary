import pytest
from decimal import Decimal

from django.contrib.auth.models import User

from backend.django_app.models import Trade, Position
from backend.execution.engine import OrderExecutionEngine
from backend.execution import mt5_connector
from backend.execution.mt5_connector import MT5BrokerConnector


@pytest.fixture
def broker(monkeypatch):
    monkeypatch.setattr(mt5_connector, "MT5_AVAILABLE", False)
    b = MT5BrokerConnector()
    b.connect("SIM-000000", "", "Simulation")
    return b


@pytest.fixture
def engine(broker):
    return OrderExecutionEngine(broker)


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="exec_tester",
        email="exec@test.com",
        password="testpass123",
    )


@pytest.mark.django_db
def test_full_trade_lifecycle(engine, user):
    """Test complete trade lifecycle: execute -> monitor -> close."""
    engine.initialize(user)

    trade = engine.execute_trade(
        user=user,
        symbol="EURUSD",
        side="BUY",
        lot_size=Decimal("0.10"),
    )
    assert trade.status == Trade.Status.EXECUTED
    assert trade.broker_order_id is not None
    assert trade.fill_price is not None

    engine.positions.sync_positions(user)
    position = Position.objects.filter(user=user, ticker="EURUSD").first()
    assert position is not None
    assert position.quantity == Decimal("0.10")

    closed = engine.close_trade(str(trade.id), user)
    assert closed is not None
    assert closed.status == Trade.Status.EXECUTED

    assert not Position.objects.filter(user=user, ticker="EURUSD").exists()


@pytest.mark.django_db
def test_risk_rejection(engine, user):
    """Test trade rejected by risk manager."""
    engine.initialize(user)

    trade = engine.execute_trade(
        user=user,
        symbol="EURUSD",
        side="BUY",
        lot_size=Decimal("1000"),
    )
    assert trade.status == Trade.Status.FAILED
    assert "Risk" in trade.notes or "risk" in trade.notes or "Position size" in trade.notes


@pytest.mark.django_db
def test_trade_history(engine, user):
    """Test trade history retrieval."""
    engine.initialize(user)

    for _ in range(3):
        engine.execute_trade(
            user=user,
            symbol="EURUSD",
            side="BUY",
            lot_size=Decimal("0.10"),
        )

    history = engine.get_trade_history(user)
    assert len(history) == 3
    assert all(h["status"] == Trade.Status.EXECUTED for h in history)


@pytest.mark.django_db
def test_daily_summary(engine, user):
    """Test daily summary generation."""
    engine.initialize(user)

    engine.execute_trade(
        user=user,
        symbol="EURUSD",
        side="BUY",
        lot_size=Decimal("0.10"),
    )

    summary = engine.get_daily_summary(user)
    assert "date" in summary
    assert "total_trades" in summary
    assert "executed_trades" in summary
    assert "total_pnl" in summary
    assert "total_commission" in summary
    assert "net_pnl" in summary
    assert "risk_status" in summary
    assert summary["total_trades"] >= 1
    assert summary["executed_trades"] >= 1
