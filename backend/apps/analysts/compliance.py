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
        # TODO: Replace with real compliance checks
        return {
            'regulatory_checks_passed': True,
            'within_position_limits': True,
            'within_exposure_limits': True,
            'violations': [],
            'max_position_size': 100000,
            'current_exposure': 45000,
            'regulatory_framework': 'MiFID II',
        }

    def _evaluate_compliance(self, regulatory_ok: bool, position_ok: bool, exposure_ok: bool, violations: list) -> tuple:
        if not regulatory_ok or len(violations) > 0:
            return ('SELL', 0.8)
        elif position_ok and exposure_ok:
            return ('HOLD', 0.6)
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
