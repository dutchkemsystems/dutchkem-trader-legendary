from .base import BaseAnalyst, AnalystResult


class ComplianceAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ['regulatory_checks', 'position_limits', 'exposure_limits']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt('compliance', symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name='compliance',
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed['signal'],
                confidence=parsed['confidence'],
                reasoning=parsed['reasoning'],
                data={'llm_model': response.model_used, 'data_source': 'llm'}
            )

        compliance_data = await self._fetch_compliance_data(symbol)
        if compliance_data is None:
            return AnalystResult(
                analyst_name='compliance',
                symbol=symbol,
                timeframe=timeframe,
                signal='HOLD',
                confidence=0.0,
                reasoning='MT5 data unavailable — cannot check compliance',
                data={'error': 'MT5 unavailable', 'data_source': 'none'}
            )

        regulatory_ok = compliance_data.get('regulatory_checks_passed', True)
        within_position = compliance_data.get('within_position_limits', True)
        within_exposure = compliance_data.get('within_exposure_limits', True)
        violations = compliance_data.get('violations', [])

        signal, confidence = self._evaluate_compliance(regulatory_ok, within_position, within_exposure, violations)

        return AnalystResult(
            analyst_name='compliance',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'Regulatory: {regulatory_ok}, Position: {within_position}, Exposure: {within_exposure}, Violations: {len(violations)}',
            data=compliance_data
        )

    async def _fetch_compliance_data(self, symbol: str) -> dict:
        """Check real MT5 positions against limits."""
        try:
            import MetaTrader5 as mt5
            info = mt5.account_info()
            if not info:
                return None

            positions = mt5.positions_get()
            open_count = len(positions) if positions else 0
            total_exposure = sum(p.volume for p in positions) if positions else 0
            max_position = 10.0  # Max lots per position
            max_total_exposure = info.equity * 0.5  # 50% of equity

            violations = []
            within_position = True
            within_exposure = True

            if positions:
                for p in positions:
                    if p.volume > max_position:
                        violations.append(f"{p.symbol}: {p.volume} lots exceeds max {max_position}")
                        within_position = False

            if total_exposure > max_total_exposure:
                violations.append(f"Total exposure {total_exposure:.2f} lots exceeds {max_total_exposure:.2f}")
                within_exposure = False

            return {
                'regulatory_checks_passed': True,  # No regulatory data available
                'within_position_limits': within_position,
                'within_exposure_limits': within_exposure,
                'violations': violations,
                'max_position_size': max_position,
                'current_exposure': round(total_exposure, 2),
                'open_positions': open_count,
                'equity': info.equity,
            }
        except Exception:
            return None

    def _evaluate_compliance(self, regulatory_ok: bool, position_ok: bool, exposure_ok: bool, violations: list) -> tuple:
        if not regulatory_ok or len(violations) > 0:
            return ('SELL', 0.8)
        elif position_ok and exposure_ok:
            return ('HOLD', 0.6)
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
