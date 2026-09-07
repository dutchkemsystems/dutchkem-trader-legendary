from __future__ import annotations

import logging

from celery import shared_task
from django.contrib.auth.models import User

from execution.engine import OrderExecutionEngine
from execution.mt5_connector import MT5Connector

logger = logging.getLogger(__name__)

_broker: MT5Connector | None = None


def _get_broker() -> MT5BrokerConnector:
    global _broker
    if _broker is None:
        _broker = MT5BrokerConnector()
    return _broker


def _get_engine() -> OrderExecutionEngine:
    return OrderExecutionEngine(broker=_get_broker())


@shared_task(bind=True, max_retries=3)
def monitor_positions(self):
    """Monitor all open positions for stop-loss/take-profit hits."""
    try:
        engine = _get_engine()
        users = User.objects.all()
        total_closed = 0

        for user in users:
            try:
                engine.initialize(user)
                trades = engine.positions.check_risk_exits(user)
                total_closed += len(trades)
            except Exception as e:
                logger.error(
                    "monitor_positions failed for user %s: %s", user.id, e
                )

        logger.info("monitor_positions completed: closed %d positions", total_closed)
        return {"closed_positions": total_closed}
    except Exception as e:
        logger.error("monitor_positions failed: %s", e)
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3)
def update_position_pnl(self):
    """Update P&L for all open positions."""
    try:
        engine = _get_engine()
        users = User.objects.all()
        total_updated = 0

        for user in users:
            try:
                engine.initialize(user)
                updated = engine.positions.update_pnl(user)
                total_updated += len(updated)
            except Exception as e:
                logger.error(
                    "update_position_pnl failed for user %s: %s", user.id, e
                )

        logger.info("update_position_pnl completed: updated %d positions", total_updated)
        return {"updated_positions": total_updated}
    except Exception as e:
        logger.error("update_position_pnl failed: %s", e)
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=3)
def sync_positions(self):
    """Sync broker positions with database."""
    try:
        engine = _get_engine()
        users = User.objects.all()
        total_synced = 0

        for user in users:
            try:
                engine.initialize(user)
                synced = engine.positions.sync_positions(user)
                total_synced += len(synced)
            except Exception as e:
                logger.error(
                    "sync_positions failed for user %s: %s", user.id, e
                )

        logger.info("sync_positions completed: synced %d positions", total_synced)
        return {"synced_positions": total_synced}
    except Exception as e:
        logger.error("sync_positions failed: %s", e)
        raise self.retry(exc=e)


@shared_task
def reset_daily_counters():
    """Reset daily risk counters (call at midnight)."""
    try:
        engine = _get_engine()
        users = User.objects.all()
        reset_count = 0

        for user in users:
            try:
                engine.initialize(user)
                engine.risk.reset_daily()
                reset_count += 1
            except Exception as e:
                logger.error(
                    "reset_daily_counters failed for user %s: %s", user.id, e
                )

        logger.info("reset_daily_counters completed: reset %d users", reset_count)
        return {"reset_users": reset_count}
    except Exception as e:
        logger.error("reset_daily_counters failed: %s", e)
        return {"error": str(e)}
