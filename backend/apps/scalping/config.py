"""Scalping strategies configuration.

Single source of truth for all scalping strategy parameters.
Feature flags are managed here — NOT duplicated in unified_engine.py.
"""

from typing import Dict, Any, List


SCALPING_GLOBAL_CONFIG: Dict[str, Any] = {
    'magic_base': 234010,  # MT5 magic numbers: 234010-234019
    'daily_loss_limit_pct': 2.0,
    'risk_per_trade_pct': 0.5,
    'min_rr': 1.5,
    'max_spread_pips': 1.5,
    'max_concurrent_scalps': 4,
    'sessions': [
        {'start': '07:00', 'end': '16:00', 'name': 'London'},
        {'start': '12:00', 'end': '21:00', 'name': 'NY'},
    ],
}

SCALPING_STRATEGIES: Dict[str, Dict[str, Any]] = {
    'chiaroscuro': {
        'enabled': False,
        'tp_pips': 20,
        'sl_pips': 12,
        'min_confidence': 0.6,
        'require_order_block': True,
        'require_fvg': True,
    },
    'london_ny_overlap': {
        'enabled': False,
        'session_start': '13:00',
        'session_end': '17:00',
        'tp_pips': 15,
        'sl_pips': 10,
        'bb_squeeze_threshold': 0.02,
    },
    'checklist_5point': {
        'enabled': False,
        'tp_pips': 15,
        'sl_pips': 10,
        'min_conditions': 5,
    },
    'autolot_20pip': {
        'enabled': False,
        'tp_pips': 20,
        'sl_pips': 20,
        'ema_fast': 10,
        'ema_slow': 20,
        'rsi_period': 14,
        'adx_threshold': 25,
    },
    'renko_20pip': {
        'enabled': False,
        'brick_size_pips': 10,
        'tp_pips': 20,
        'sl_pips': 20,
    },
    'sniper': {
        'enabled': False,
        'tp_pips': 15,
        'sl_pips': 10,
        'require_rejection_candle': True,
        'lookback_periods': 20,
    },
    'ema_pullback': {
        'enabled': False,
        'tp_pips': 20,
        'sl_pips': 12,
        'ema_fast': 10,
        'ema_slow': 20,
    },
    'session_breakout': {
        'enabled': False,
        'session_open_gmt': '08:00',
        'range_minutes': 60,
        'tp_pips': 15,
        'sl_pips': 10,
    },
    'news_fade': {
        'enabled': False,
        'events': ['NFP', 'CPI', 'FOMC'],
        'wait_minutes': 5,
        'tp_pips': 12,
        'sl_pips': 8,
    },
    'fvg_confluence': {
        'enabled': False,
        'htf': 'H4',
        'entry_tf': 'M5',
        'tp_pips': 15,
        'sl_pips': 10,
    },
    'smart_machine_ea': {
        'enabled': False,
        'htf': 'H4',
        'entry_tf': 'M15',
        'tp_pips': 15,
        'sl_pips': 10,
        'min_confidence': 0.6,
        'ml_confidence_threshold': 0.60,
    },
    'gold_hedge_ea': {
        'enabled': False,
        'symbol': 'XAUUSD',
        'htf': 'H4',
        'entry_tf': 'M5',
        'lot_progression': [0.01, 0.02, 0.03, 0.05, 0.08],
        'max_hedge_levels': 5,
        'basket_tp_usd': 50.0,
        'min_profit_floor_usd': 10.0,
        'freeze_loss_usd': 200.0,
        'trailing_tp_enabled': True,
        'trailing_tp_step_usd': 10.0,
        'hedge_distance_atr': 1.5,
        'ema_fast': 20,
        'ema_slow': 50,
        'rsi_period': 14,
        'atr_period': 14,
        'check_interval_seconds': 60,
        'magic_base': 234020,
    },
    'quantum_ai': {
        'enabled': True,
        'htf': 'H4',
        'entry_tf': 'M15',
        'tp_pips': 15,
        'sl_pips': 10,
        'min_quantum_score': 0.3,
        'min_confidence': 0.6,
        'require_vsa': True,
        'require_perceptron': True,
        'memory_boost': 0.1,
        'magic_base': 234030,
    },
}


def get_enabled_strategies() -> Dict[str, bool]:
    """Return dict of strategy_name -> enabled status."""
    return {name: config.get('enabled', False) for name, config in SCALPING_STRATEGIES.items()}


def is_any_strategy_enabled() -> bool:
    """Check if any scalping strategy is enabled."""
    return any(config.get('enabled', False) for config in SCALPING_STRATEGIES.values())


def get_strategy_config(strategy_name: str) -> Dict[str, Any]:
    """Get configuration for a specific strategy."""
    return SCALPING_STRATEGIES.get(strategy_name, {})
