"""
Feature 5: Economic Calendar Integration
Fetch high-impact events and block trades during news windows.
"""
import os
import json
import logging
from typing import Dict, List
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger("calendar")

# High-impact events that cause major volatility
HIGH_IMPACT_EVENTS = [
    "NFP", "Non-Farm Payrolls", "FOMC", "Fed Rate", "CPI", "Inflation",
    "GDP", "Retail Sales", "PMI", "Employment", "Unemployment",
    "ECB Rate", "BOE Rate", "BOJ Rate", "RBA Rate", "SNB Rate",
    "Trade Balance", "Industrial Production", "Housing Starts",
]

MEDIUM_IMPACT_EVENTS = [
    "Jobless Claims", "Consumer Confidence", "Producer Price",
    "Factory Orders", "Durable Goods", "Leading Indicators",
]


class EconomicCalendar:
    """Manage economic calendar events and trading blackouts."""

    def __init__(self, data_dir: str = None):
        self.events = []
        self.blackout_minutes = 30
        self.data_dir = Path(data_dir) if data_dir else Path("unified_data")
        self.data_dir.mkdir(exist_ok=True)
        self.cache_file = self.data_dir / "calendar_cache.json"
        self._load_cache()

    def _load_cache(self):
        """Load cached events from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r") as f:
                    data = json.load(f)
                    self.events = data.get("events", [])
                    log.info(f"Loaded {len(self.events)} cached calendar events")
            except Exception as e:
                log.warning(f"Failed to load calendar cache: {e}")

    def _save_cache(self):
        """Save events to disk."""
        try:
            with open(self.cache_file, "w") as f:
                json.dump({"events": self.events, "updated": datetime.now(timezone.utc).isoformat()}, f)
        except Exception as e:
            log.warning(f"Failed to save calendar cache: {e}")

    def fetch_events(self) -> List[Dict]:
        """Fetch events from hardcoded list."""
        from apps.calendar.events import get_all_events
        self.events = get_all_events()
        self._save_cache()
        log.info(f"Fetched {len(self.events)} economic events")
        return self.events

    def _fetch_forex_factory(self) -> List[Dict]:
        """Fetch from Forex Factory (scraping required, placeholder)."""
        # In production, would scrape forexFactory.com
        # For now, return cached or empty
        return []

    def _fetch_trading_economics(self, api_key: str) -> List[Dict]:
        """Fetch from Trading Economics API."""
        import requests

        url = "https://api.tradingeconomics.com/calendar"
        params = {
            "c": api_key,
            "f": "json",
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        events = []
        for item in data:
            if item.get("Importance") == 3:  # High impact
                events.append({
                    "title": item.get("Event", ""),
                    "country": item.get("Country", ""),
                    "date": item.get("Date", ""),
                    "impact": "high",
                    "forecast": item.get("Forecast", ""),
                    "previous": item.get("Previous", ""),
                })

        return events

    def is_blackout_period(self, symbol: str = None) -> Dict:
        """Check if we're in a blackout period."""
        now = datetime.now(timezone.utc)

        for event in self.events:
            try:
                event_time = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
            except (ValueError, KeyError):
                continue

            blackout_start = event_time - timedelta(minutes=self.blackout_minutes)
            blackout_end = event_time + timedelta(minutes=self.blackout_minutes)

            if blackout_start <= now <= blackout_end:
                return {
                    "blackout": True,
                    "event": event.get("title", "Unknown"),
                    "impact": event.get("impact", "unknown"),
                    "ends_at": blackout_end.isoformat(),
                }

        return {"blackout": False, "reason": "no_upcoming_events"}

    def get_upcoming_events(self, hours: int = 24) -> List[Dict]:
        """Get upcoming events within specified hours."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours)

        upcoming = []
        for event in self.events:
            try:
                event_time = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
                if now <= event_time <= cutoff:
                    upcoming.append(event)
            except (ValueError, KeyError):
                continue

        return sorted(upcoming, key=lambda e: e.get("date", ""))

    def should_block_trade(self, symbol: str = None) -> Dict:
        """Determine if trading should be blocked."""
        from apps.calendar.events import is_blackout_period
        blackout = is_blackout_period()

        if blackout["blackout"]:
            return {
                "block": True,
                "reason": f"news_blackout_{blackout['event']}",
                "event": blackout["event"],
            }

        return {"block": False, "reason": "clear_to_trade"}
