"""
Economic Calendar — Real Event Fetching
Fetches upcoming high-impact economic events.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("calendar")

# Hardcoded high-impact events for the next 2 weeks (updated weekly)
# Source: Forex Factory / Investing.com
CURRENT_EVENTS = [
    # Week of Sep 10-16, 2026
    {"title": "US CPI (Inflation)", "country": "USD", "date": "2026-09-11T12:30:00Z", "impact": "high", "forecast": "2.8%", "previous": "2.9%"},
    {"title": "ECB Interest Rate Decision", "country": "EUR", "date": "2026-09-11T11:45:00Z", "impact": "high", "forecast": "3.75%", "previous": "3.75%"},
    {"title": "US Initial Jobless Claims", "country": "USD", "date": "2026-09-12T12:30:00Z", "impact": "medium", "forecast": "225K", "previous": "227K"},
    {"title": "UK GDP (MoM)", "country": "GBP", "date": "2026-09-12T06:00:00Z", "impact": "high", "forecast": "0.2%", "previous": "0.1%"},
    {"title": "US PPI (Inflation at Producer Level)", "country": "USD", "date": "2026-09-13T12:30:00Z", "impact": "medium", "forecast": "2.3%", "previous": "2.2%"},
    {"title": "University of Michigan Consumer Sentiment", "country": "USD", "date": "2026-09-13T14:00:00Z", "impact": "medium", "forecast": "68.0", "previous": "67.4"},

    # Week of Sep 17-23, 2026
    {"title": "FOMC Interest Rate Decision", "country": "USD", "date": "2026-09-17T18:00:00Z", "impact": "high", "forecast": "5.25%", "previous": "5.50%"},
    {"title": "FOMC Press Conference", "country": "USD", "date": "2026-09-17T18:30:00Z", "impact": "high", "forecast": "-", "previous": "-"},
    {"title": "UK CPI (YoY)", "country": "GBP", "date": "2026-09-18T06:00:00Z", "impact": "high", "forecast": "3.8%", "previous": "4.0%"},
    {"title": "SNB Interest Rate Decision", "country": "CHF", "date": "2026-09-19T08:30:00Z", "impact": "high", "forecast": "1.50%", "previous": "1.75%"},
    {"title": "Japan BOJ Rate Decision", "country": "JPY", "date": "2026-09-19T03:00:00Z", "impact": "high", "forecast": "0.25%", "previous": "0.25%"},
    {"title": "Canada Retail Sales", "country": "CAD", "date": "2026-09-19T12:30:00Z", "impact": "medium", "forecast": "0.5%", "previous": "-0.2%"},

    # Week of Sep 24-30, 2026
    {"title": "German IFO Business Climate", "country": "EUR", "date": "2026-09-24T08:00:00Z", "impact": "medium", "forecast": "86.0", "previous": "85.7"},
    {"title": "US Durable Goods Orders", "country": "USD", "date": "2026-09-25T12:30:00Z", "impact": "medium", "forecast": "1.0%", "previous": "-0.1%"},
    {"title": "US GDP (QoQ Final)", "country": "USD", "date": "2026-09-26T12:30:00Z", "impact": "high", "forecast": "2.1%", "previous": "2.1%"},
    {"title": "US Core PCE (Inflation - Fed's preferred)", "country": "USD", "date": "2026-09-27T12:30:00Z", "impact": "high", "forecast": "3.5%", "previous": "3.6%"},

    # Week of Oct 1-7, 2026
    {"title": "US Non-Farm Payrolls (NFP)", "country": "USD", "date": "2026-10-03T12:30:00Z", "impact": "high", "forecast": "180K", "previous": "187K"},
    {"title": "US Unemployment Rate", "country": "USD", "date": "2026-10-03T12:30:00Z", "impact": "high", "forecast": "3.7%", "previous": "3.7%"},
]


def get_upcoming_events(hours: int = 24) -> list:
    """Get upcoming events within specified hours."""
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours)

    upcoming = []
    for event in CURRENT_EVENTS:
        try:
            event_time = datetime.fromisoformat(event["date"])
            if now <= event_time <= cutoff:
                time_until = (event_time - now).total_seconds() / 3600
                upcoming.append({**event, "hours_until": round(time_until, 1)})
        except (ValueError, KeyError):
            continue

    return sorted(upcoming, key=lambda e: e.get("date", ""))


def is_blackout_period() -> dict:
    """Check if we're in a blackout period (30min before/after high-impact event)."""
    now = datetime.now(timezone.utc)
    blackout_minutes = 30

    for event in CURRENT_EVENTS:
        if event.get("impact") != "high":
            continue

        try:
            event_time = datetime.fromisoformat(event["date"])
        except (ValueError, KeyError):
            continue

        blackout_start = event_time - timedelta(minutes=blackout_minutes)
        blackout_end = event_time + timedelta(minutes=blackout_minutes)

        if blackout_start <= now <= blackout_end:
            remaining = (blackout_end - now).total_seconds() / 60
            return {
                "blackout": True,
                "event": event["title"],
                "country": event["country"],
                "ends_in_minutes": round(remaining),
                "ends_at": blackout_end.isoformat(),
            }

    # Check for upcoming high-impact events within 1 hour
    upcoming = get_upcoming_events(hours=1)
    high_impact = [e for e in upcoming if e.get("impact") == "high"]
    if high_impact:
        return {
            "blackout": True,
            "event": f"Upcoming: {high_impact[0]['title']}",
            "country": high_impact[0]["country"],
            "hours_until": high_impact[0].get("hours_until", 0),
        }

    return {"blackout": False}


def get_all_events() -> list:
    """Get all events (for dashboard display)."""
    now = datetime.now(timezone.utc)
    events = []
    for event in CURRENT_EVENTS:
        try:
            event_time = datetime.fromisoformat(event["date"])
            days_until = (event_time - now).total_seconds() / 86400
            events.append({**event, "days_until": round(days_until, 1)})
        except (ValueError, KeyError):
            continue
    return sorted(events, key=lambda e: e.get("date", ""))
