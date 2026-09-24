import os
import asyncio
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass

import MetaTrader5 as mt5
import numpy as np


MT5_TIMEFRAMES = {
    '1M': mt5.TIMEFRAME_M1,
    '5M': mt5.TIMEFRAME_M5,
    '15M': mt5.TIMEFRAME_M15,
    '1H': mt5.TIMEFRAME_H1,
    '4H': mt5.TIMEFRAME_H4,
    '1D': mt5.TIMEFRAME_D1,
}

MT5_CONFIG = {
    "path": r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe",
    "login": int(os.environ.get("MT5_LOGIN", "0")),
    "password": os.environ.get("MT5_PASSWORD", ""),
    "server": os.environ.get("MT5_SERVER", ""),
}


@dataclass
class TimeframeResult:
    timeframe: str
    signal: str
    confidence: float
    data: Dict[str, Any]


@dataclass
class ScanResult:
    symbol: str
    timeframes: Dict[str, TimeframeResult]
    h1_bias: str
    alignment: float
    overall_signal: str
    overall_confidence: float


def _compute_rsi(closes: np.ndarray, period: int = 14) -> float:
    deltas = np.diff(closes[-period - 1:])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains) if len(gains) > 0 else 0.0
    avg_loss = np.mean(losses) if len(losses) > 0 else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _compute_sma(values: np.ndarray, period: int) -> float:
    if len(values) < period:
        return values[-1] if len(values) > 0 else 0.0
    return float(np.mean(values[-period:]))


def _compute_macd(closes: np.ndarray) -> Tuple[float, float, float]:
    n = len(closes)
    k12 = 2.0 / 13.0
    k26 = 2.0 / 27.0
    ema12 = np.zeros(n)
    ema26 = np.zeros(n)
    ema12[0] = closes[0]
    ema26[0] = closes[0]
    for i in range(1, n):
        ema12[i] = closes[i] * k12 + ema12[i - 1] * (1 - k12)
        ema26[i] = closes[i] * k26 + ema26[i - 1] * (1 - k26)
    macd_line = ema12 - ema26
    signal = np.zeros(n)
    k9 = 2.0 / 10.0
    signal[0] = macd_line[0]
    for i in range(1, n):
        signal[i] = macd_line[i] * k9 + signal[i - 1] * (1 - k9)
    histogram = macd_line - signal
    return float(macd_line[-1]), float(signal[-1]), float(histogram[-1])


def _compute_bollinger(closes: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Tuple[float, float, float]:
    if len(closes) < period:
        mid = float(np.mean(closes))
        return mid, mid, mid
    sma = float(np.mean(closes[-period:]))
    std = float(np.std(closes[-period:]))
    return sma - std_dev * std, sma, sma + std_dev * std


def _compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < 2:
        return 0.0
    trs = np.zeros(len(closes) - 1)
    for i in range(1, len(closes)):
        trs[i - 1] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
    if len(trs) < period:
        return float(np.mean(trs))
    return float(np.mean(trs[-period:]))


def _signal_from_indicators(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray) -> Tuple[str, float, Dict[str, Any]]:
    rsi = _compute_rsi(closes)
    macd_line, signal_line, histogram = _compute_macd(closes)
    sma20 = _compute_sma(closes, 20)
    sma50 = _compute_sma(closes, 50)
    bb_lower, bb_mid, bb_upper = _compute_bollinger(closes)
    atr = _compute_atr(highs, lows, closes)
    price = float(closes[-1])

    score = 0
    signals_detail = {}

    if rsi < 35:
        score += 1
        signals_detail['rsi'] = f'BUY (RSI={rsi:.1f})'
    elif rsi > 65:
        score -= 1
        signals_detail['rsi'] = f'SELL (RSI={rsi:.1f})'
    else:
        signals_detail['rsi'] = f'NEUTRAL (RSI={rsi:.1f})'

    if histogram > 0:
        score += 1
        signals_detail['macd'] = f'BUY (hist={histogram:.6f})'
    elif histogram < 0:
        score -= 1
        signals_detail['macd'] = f'SELL (hist={histogram:.6f})'
    else:
        signals_detail['macd'] = 'NEUTRAL'

    if price > sma20 > sma50:
        score += 1
        signals_detail['sma'] = f'BUY (price>{sma20:.5f}>{sma50:.5f})'
    elif price < sma20 < sma50:
        score -= 1
        signals_detail['sma'] = f'SELL (price<{sma20:.5f}<{sma50:.5f})'
    else:
        signals_detail['sma'] = f'NEUTRAL (price={price:.5f}, SMA20={sma20:.5f}, SMA50={sma50:.5f})'

    if price < bb_lower:
        score += 1
        signals_detail['bollinger'] = f'BUY (price {price:.5f} < lower {bb_lower:.5f})'
    elif price > bb_upper:
        score -= 1
        signals_detail['bollinger'] = f'SELL (price {price:.5f} > upper {bb_upper:.5f})'
    else:
        signals_detail['bollinger'] = f'NEUTRAL (in bands {bb_lower:.5f}-{bb_upper:.5f})'

    if score >= 2:
        signal = 'BUY'
    elif score <= -2:
        signal = 'SELL'
    else:
        signal = 'HOLD'

    confidence = min(abs(score) / 4.0, 1.0)

    data = {
        'price': price,
        'rsi': round(rsi, 2),
        'macd': round(macd_line, 8),
        'macd_signal': round(signal_line, 8),
        'macd_histogram': round(histogram, 8),
        'sma20': round(sma20, 5),
        'sma50': round(sma50, 5),
        'bollinger_lower': round(bb_lower, 5),
        'bollinger_mid': round(bb_mid, 5),
        'bollinger_upper': round(bb_upper, 5),
        'atr': round(atr, 5),
        'score': score,
        'indicators': signals_detail,
    }

    return signal, confidence, data


class MultiTimeframeScanner:
    def __init__(self):
        self.timeframes = ['1M', '5M', '15M', '1H', '4H', '1D']

    async def scan(self, symbol: str) -> ScanResult:
        tasks = [self._analyze_timeframe(symbol, tf) for tf in self.timeframes]
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=15.0
            )
        except asyncio.TimeoutError:
            # Return partial results from whatever completed
            results = [TimeframeResult(timeframe=tf, signal='HOLD', confidence=0.0, data={'error': 'timeout'})
                       for tf in self.timeframes]

        # Filter out exceptions, replace with HOLD
        clean_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                clean_results.append(TimeframeResult(
                    timeframe=self.timeframes[i], signal='HOLD', confidence=0.0,
                    data={'error': str(r)}
                ))
            else:
                clean_results.append(r)

        timeframe_results = {r.timeframe: r for r in clean_results}

        h1_bias = timeframe_results['1H'].signal

        for tf in ['1M', '5M', '15M']:
            if timeframe_results[tf].signal != h1_bias:
                timeframe_results[tf] = TimeframeResult(
                    timeframe=tf,
                    signal=timeframe_results[tf].signal,
                    confidence=timeframe_results[tf].confidence * 0.5,
                    data=timeframe_results[tf].data
                )

        alignment = self._calculate_alignment(timeframe_results)
        overall_signal, overall_confidence = self._aggregate_signals(timeframe_results)

        return ScanResult(
            symbol=symbol,
            timeframes=timeframe_results,
            h1_bias=h1_bias,
            alignment=alignment,
            overall_signal=overall_signal,
            overall_confidence=overall_confidence
        )

    async def _analyze_timeframe(self, symbol: str, timeframe: str) -> TimeframeResult:
        mt5_tf = MT5_TIMEFRAMES.get(timeframe, mt5.TIMEFRAME_H1)

        loop = asyncio.get_event_loop()
        try:
            rates = await asyncio.wait_for(
                loop.run_in_executor(None, self._fetch_rates, symbol, mt5_tf, 200),
                timeout=8.0
            )
        except (asyncio.TimeoutError, Exception):
            rates = None

        if rates is None or len(rates) < 50:
            return TimeframeResult(
                timeframe=timeframe,
                signal='HOLD',
                confidence=0.0,
                data={'symbol': symbol, 'timeframe': timeframe, 'error': 'insufficient_data'}
            )

        closes = np.array([r['close'] for r in rates], dtype=float)
        highs = np.array([r['high'] for r in rates], dtype=float)
        lows = np.array([r['low'] for r in rates], dtype=float)

        signal, confidence, data = _signal_from_indicators(closes, highs, lows)
        data['symbol'] = symbol
        data['timeframe'] = timeframe
        data['candles'] = len(rates)

        return TimeframeResult(
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            data=data
        )

    @staticmethod
    def _fetch_rates(symbol: str, timeframe: int, count: int):
        try:
            initialized = mt5.initialize(**MT5_CONFIG)
            if not initialized:
                return None
            try:
                rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
                return rates
            finally:
                mt5.shutdown()
        except Exception:
            return None

    def _calculate_alignment(self, results: Dict[str, TimeframeResult]) -> float:
        signals = [r.signal for r in results.values()]
        buy_count = signals.count('BUY')
        sell_count = signals.count('SELL')
        total = len(signals)
        return max(buy_count, sell_count) / total if total > 0 else 0

    def _aggregate_signals(self, results: Dict[str, TimeframeResult]) -> Tuple[str, float]:
        weights = {'1M': 0.1, '5M': 0.15, '15M': 0.2, '1H': 0.25, '4H': 0.3, '1D': 0.35}
        total_weight = sum(weights.values())

        buy_score = sum(weights[tf] for tf, r in results.items() if r.signal == 'BUY') / total_weight
        sell_score = sum(weights[tf] for tf, r in results.items() if r.signal == 'SELL') / total_weight

        if buy_score > sell_score:
            return ('BUY', min(buy_score, 1.0))
        elif sell_score > buy_score:
            return ('SELL', min(sell_score, 1.0))
        return ('HOLD', 0.5)
