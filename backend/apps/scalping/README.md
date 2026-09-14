# Scalping Strategies Module

10 independent scalping strategies running parallel to the main D-T Ventures trading engine.

## Overview

This module adds 10 scalping strategies that extract 10-20 pips from the market at the earliest opportunity. Each strategy is independently toggleable via feature flags (default OFF).

## Strategies

| # | Strategy | Timeframes | Target |
|---|----------|------------|--------|
| 1 | London/NY Overlap | M1, M5 | 15 pips |
| 2 | Chiaroscuro | M5, M15, H1 | 20 pips |
| 3 | 5-Point Checklist | M5, H1 | 15 pips |
| 4 | AutoLot 20-Pip | M5 | 20 pips |
| 5 | Renko 20-Pip | M5 (Renko) | 20 pips |
| 6 | Sniper | M1, M5 | 15 pips |
| 7 | EMA Pullback | M5 | 20 pips |
| 8 | Session Open Breakout | M5, M15 | 15 pips |
| 9 | News Fade | M1, M5 | 12 pips |
| 10 | FVG Confluence | M5, H4 | 15 pips |

## Enabling Strategies

Edit `backend/apps/scalping/config.py`:

```python
SCALPING_STRATEGIES = {
    'chiaroscuro': {
        'enabled': True,  # Set to True to enable
        ...
    },
}
```

Or use the API toggle endpoint:

```bash
POST /api/v1/scalping/toggle/chiaroscuro
{"enabled": true}
```

## Risk Management

All strategies enforce:
- Daily Loss Limit: 2%
- Risk Per Trade: 0.5%
- Minimum R:R: 1:1.5
- Circuit Breaker: 3 consecutive losses
- Spread Filter: > 1.5 pips
- Session Filter: London/NY only
- Max Concurrent Scalps: 4

## API Endpoints

- `GET /api/v1/scalping/status` — Get strategy status
- `POST /api/v1/scalping/toggle/{name}` — Toggle strategy

## Architecture

```
backend/apps/scalping/
├── __init__.py
├── base.py              # ScalpingStrategy ABC
├── signals.py           # ScalpSignal dataclass
├── config.py            # All strategy configurations
├── engine.py            # ScalpingEngine (parallel runner)
├── indicators/          # Shared indicators
├── strategies/          # 10 strategy implementations
└── tests/               # Unit + integration tests
```
