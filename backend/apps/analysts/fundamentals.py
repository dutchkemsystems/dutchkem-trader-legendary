from .base import BaseAnalyst, AnalystResult


class FundamentalsAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ['financial_ratios', 'balance_sheet', 'cash_flow', 'income_statement']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt('fundamentals', symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name='fundamentals',
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed['signal'],
                confidence=parsed['confidence'],
                reasoning=parsed['reasoning'],
                data={'llm_model': response.model_used, 'data_source': 'llm'}
            )

        financials = await self._fetch_financials(symbol)
        ratios = self._calculate_ratios(financials)
        score = self._score_fundamentals(ratios)

        if score > 0.3:
            signal = 'BUY'
            confidence = min(0.5 + score, 0.85)
        elif score < -0.3:
            signal = 'SELL'
            confidence = min(0.5 + abs(score), 0.85)
        else:
            signal = 'HOLD'
            confidence = 0.5

        return AnalystResult(
            analyst_name='fundamentals',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'Score: {score:.2f}, P/E: {ratios.get("pe_ratio", "N/A")}',
            data={'ratios': ratios, 'score': score}
        )

    async def _fetch_financials(self, symbol: str) -> dict:
        # TODO: Replace with real financial API
        return {'pe_ratio': 15.2, 'pb_ratio': 2.1, 'roe': 0.18, 'debt_to_equity': 0.45}

    def _calculate_ratios(self, financials: dict) -> dict:
        return {
            'pe_ratio': financials.get('pe_ratio', 0),
            'pb_ratio': financials.get('pb_ratio', 0),
            'roe': financials.get('roe', 0),
            'debt_to_equity': financials.get('debt_to_equity', 0)
        }

    def _score_fundamentals(self, ratios: dict) -> float:
        score = 0.0
        if 0 < ratios.get('pe_ratio', 0) < 20:
            score += 0.2
        elif ratios.get('pe_ratio', 0) > 30:
            score -= 0.2
        if ratios['roe'] > 0.15:
            score += 0.2
        if ratios['debt_to_equity'] < 0.5:
            score += 0.1
        return score

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
