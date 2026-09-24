import asyncio

from .base import BaseAnalyst, AnalystResult


class QuantAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ['stat_arb', 'mean_reversion', 'cointegration', 'momentum']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt('quant', symbol, timeframe)
            response = await asyncio.to_thread(self.llm_client.analyze, prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name='quant',
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed['signal'],
                confidence=parsed['confidence'],
                reasoning=parsed['reasoning'],
                data={'llm_model': response.model_used, 'data_source': 'llm'}
            )

        quant_data = await self._fetch_quant_data(symbol)
        if quant_data is None:
            return AnalystResult(
                analyst_name='quant',
                symbol=symbol,
                timeframe=timeframe,
                signal='HOLD',
                confidence=0.0,
                reasoning='MT5 data unavailable — cannot run quant analysis',
                data={'error': 'MT5 unavailable', 'data_source': 'none'}
            )
        stat_arb = quant_data.get('stat_arb_zscore', 0.0)
        mean_rev = quant_data.get('mean_reversion_signal', 0.0)
        coint_score = quant_data.get('cointegration_score', 0.0)
        momentum = quant_data.get('momentum_score', 0.0)

        signal, confidence = self._evaluate_quant(stat_arb, mean_rev, coint_score, momentum)

        return AnalystResult(
            analyst_name='quant',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'StArb: {stat_arb:.2f}, MRev: {mean_rev:.2f}, Coint: {coint_score:.2f}, Mom: {momentum:.2f}',
            data=quant_data
        )

    async def _fetch_quant_data(self, symbol: str) -> dict:
        try:
            import MetaTrader5 as mt5
            import numpy as np
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 200)
            if rates is not None and len(rates) >= 50:
                closes = np.array([r['close'] for r in rates])
                returns = np.diff(closes) / closes[:-1]
                price_mean = np.mean(closes)
                price_std = np.std(closes[-50:])
                z_score = float((closes[-1] - np.mean(closes[-50:])) / price_std) if price_std > 0 else 0.0
                mean_rev = -z_score * 0.3
                if len(returns) >= 20:
                    cum_returns = np.cumsum(returns)
                    window = 20
                    running_mean = np.convolve(returns, np.ones(window)/window, mode='valid')
                    momentum_score = float(np.mean(returns[-10:])) * 100 if len(returns) >= 10 else 0.0
                else:
                    momentum_score = 0.0
                stat_arb = float(np.mean(returns[-20:])) / (np.std(returns[-20:]) + 1e-10) if len(returns) >= 20 else 0.0
                stat_arb = max(-3, min(3, stat_arb))
                coint_score = 0.7
                if len(closes) >= 50:
                    short_ma = np.mean(closes[-10:])
                    long_ma = np.mean(closes[-50:])
                    spread_pct = (short_ma - long_ma) / long_ma if long_ma != 0 else 0
                    coint_score = float(1 - min(1, abs(spread_pct) * 100))
                half_life = 15.0
                if len(closes) >= 30:
                    spread = closes[-30:] - np.mean(closes[-30:])
                    spread_lag = spread[:-1]
                    spread_diff = np.diff(spread)
                    if len(spread_lag) > 1 and np.std(spread_lag) > 0:
                        beta = np.polyfit(spread_lag, spread_diff, 1)[0]
                        half_life = float(-np.log(2) / beta) if beta < 0 else 15.0
                        half_life = max(1, min(100, half_life))
                returns_series = returns[-100:] if len(returns) >= 100 else returns
                hurst = 0.5
                if len(returns_series) >= 20:
                    lags = range(2, min(20, len(returns_series)))
                    tau = [np.sqrt(np.std(np.subtract(returns_series[lag:], returns_series[:-lag]))) for lag in lags]
                    if len(tau) > 1 and all(t > 0 for t in tau):
                        poly = np.polyfit(np.log(list(lags)), np.log(tau), 1)
                        hurst = float(poly[0])
                        hurst = max(0, min(1, hurst))
                return {
                    'stat_arb_zscore': round(stat_arb, 4),
                    'mean_reversion_signal': round(max(-2, min(2, mean_rev)), 4),
                    'cointegration_score': round(max(0, min(1, coint_score)), 4),
                    'momentum_score': round(max(-2, min(2, momentum_score)), 4),
                    'half_life': round(half_life, 2),
                    'hurst_exponent': round(hurst, 4),
                    'z_score': round(z_score, 4),
                    'price_mean': round(float(price_mean), 5),
                    'price_std': round(float(price_std), 6),
                }
        except Exception:
            pass
        return None  # No MT5 data available

    def _evaluate_quant(self, stat_arb: float, mean_rev: float, coint: float, momentum: float) -> tuple:
        composite = (stat_arb * 0.3 + mean_rev * 0.2 + coint * 0.25 + momentum * 0.25)

        # Individual strong signals can override composite
        # Momentum > 0.15 = moderate trend (lowered from 0.3)
        if momentum > 0.15 and stat_arb > 0.05:
            return ('BUY', min(0.6 + momentum * 0.3, 0.85))
        elif momentum < -0.15 and stat_arb < -0.05:
            return ('SELL', min(0.6 + abs(momentum) * 0.3, 0.85))

        # Mean reversion: z-score reversion signal (lowered from 0.3)
        if mean_rev > 0.15:
            return ('BUY', min(0.55 + mean_rev * 0.3, 0.8))
        elif mean_rev < -0.15:
            return ('SELL', min(0.55 + abs(mean_rev) * 0.3, 0.8))

        # Composite with lower threshold (lowered from 0.3)
        if composite > 0.15:
            return ('BUY', min(0.5 + composite * 0.5, 0.85))
        elif composite < -0.15:
            return ('SELL', min(0.5 + abs(composite) * 0.5, 0.85))

        # Default: weak directional lean based on z-score (lowered from 0.5)
        if stat_arb > 0.2:
            return ('BUY', 0.55)
        elif stat_arb < -0.2:
            return ('SELL', 0.55)
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
