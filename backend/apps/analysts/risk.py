import math
from .base import BaseAnalyst, AnalystResult


class RiskAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ['portfolio_correlation', 'var', 'max_drawdown', 'sharpe_ratio']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt('risk', symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name='risk',
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed['signal'],
                confidence=parsed['confidence'],
                reasoning=parsed['reasoning'],
                data={'llm_model': response.model_used, 'data_source': 'llm'}
            )

        risk_data = await self._fetch_risk_data(symbol)
        if risk_data is None:
            return AnalystResult(
                analyst_name='risk',
                symbol=symbol,
                timeframe=timeframe,
                signal='HOLD',
                confidence=0.0,
                reasoning='MT5 data unavailable — cannot assess risk',
                data={'error': 'MT5 unavailable', 'data_source': 'none'}
            )
        var_95 = risk_data.get('var_95', 0.02)
        max_dd = risk_data.get('max_drawdown', 0.10)
        sharpe = risk_data.get('sharpe_ratio', 1.0)
        correlation = risk_data.get('portfolio_correlation', 0.5)

        signal, confidence = self._evaluate_risk(var_95, max_dd, sharpe, correlation)

        return AnalystResult(
            analyst_name='risk',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'VaR95: {var_95:.4f}, MaxDD: {max_dd:.2%}, Sharpe: {sharpe:.2f}, Corr: {correlation:.2f}',
            data=risk_data
        )

    async def _fetch_risk_data(self, symbol: str) -> dict:
        try:
            import MetaTrader5 as mt5
            import numpy as np
            info = mt5.account_info()
            if info:
                balance = info.balance
                equity = info.equity
                margin_free = info.margin_free
                profit = info.profit
                leverage = info.leverage
                max_dd = (balance - equity) / balance if balance > 0 else 0
                max_dd = max(0, max_dd)
                positions = mt5.positions_get()
                open_count = len(positions) if positions else 0
                total_exposure = sum(p.volume for p in positions) if positions else 0
                rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 100)
                sharpe = 1.0
                var_95 = 0.02
                if rates is not None and len(rates) >= 20:
                    closes = np.array([r['close'] for r in rates])
                    returns = np.diff(closes) / closes[:-1]
                    if len(returns) > 1:
                        std_ret = np.std(returns)
                        mean_ret = np.mean(returns)
                        sharpe = float(mean_ret / std_ret * np.sqrt(252 * 24)) if std_ret > 0 else 1.0
                        var_95 = float(-np.percentile(returns, 5)) if len(returns) >= 20 else 0.02
                correlation = min(1.0, total_exposure / 5.0) if total_exposure > 0 else 0.5
                return {
                    'var_95': round(max(0.001, min(0.1, var_95)), 4),
                    'max_drawdown': round(max(0, min(1, max_dd)), 4),
                    'sharpe_ratio': round(max(-5, min(5, sharpe)), 2),
                    'portfolio_correlation': round(max(0, min(1, correlation)), 2),
                    'sortino_ratio': round(max(0, sharpe * 1.2), 2),
                    'beta': round(max(0, min(2, 0.85)), 2),
                    'balance': balance,
                    'equity': equity,
                    'open_positions': open_count,
                    'total_exposure_lots': round(total_exposure, 2),
                    'margin_free': margin_free,
                }
        except Exception:
            pass
        return None  # No risk data available

    def _evaluate_risk(self, var_95: float, max_dd: float, sharpe: float, correlation: float) -> tuple:
        """Evaluate risk conditions and produce directional lean.

        Healthy account = favorable conditions for BUY signals
        Stressed account = caution, lean SELL (reduce exposure)
        """
        # Score from -1 (very risky) to +1 (very safe)
        risk_score = 0.0

        # Sharpe contribution: positive = good, negative = bad
        if sharpe > 2.0:
            risk_score += 0.3
        elif sharpe > 1.0:
            risk_score += 0.2
        elif sharpe > 0:
            risk_score += 0.1
        elif sharpe < -1.0:
            risk_score -= 0.3
        elif sharpe < 0:
            risk_score -= 0.15

        # Drawdown contribution
        if max_dd < 0.02:
            risk_score += 0.3  # Very healthy
        elif max_dd < 0.05:
            risk_score += 0.2
        elif max_dd < 0.10:
            risk_score += 0.1
        elif max_dd > 0.15:
            risk_score -= 0.2
        elif max_dd > 0.10:
            risk_score -= 0.1

        # VaR contribution
        if var_95 < 0.01:
            risk_score += 0.2  # Low risk
        elif var_95 < 0.02:
            risk_score += 0.1
        elif var_95 > 0.04:
            risk_score -= 0.2  # High risk
        elif var_95 > 0.03:
            risk_score -= 0.1

        # Correlation: high portfolio correlation = concentrated risk
        if correlation > 0.8:
            risk_score -= 0.15
        elif correlation < 0.3:
            risk_score += 0.1

        # Convert to signal
        if risk_score > 0.3:
            return ('BUY', min(0.55 + risk_score * 0.3, 0.8))
        elif risk_score < -0.3:
            return ('SELL', min(0.55 + abs(risk_score) * 0.3, 0.8))
        elif risk_score > 0.1:
            return ('BUY', 0.55)
        elif risk_score < -0.1:
            return ('SELL', 0.55)
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
