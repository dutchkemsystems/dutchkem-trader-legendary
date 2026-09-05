from .base import BaseAnalyst, AnalystResult


class MacroAnalyst(BaseAnalyst):
    def __init__(self):
        self._capabilities = ['gdp', 'inflation', 'interest_rates', 'employment']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        macro_data = await self._fetch_macro_data(symbol)
        gdp_growth = macro_data.get('gdp_growth', 2.0)
        inflation = macro_data.get('inflation_rate', 2.0)
        interest_rate = macro_data.get('interest_rate', 5.0)
        employment = macro_data.get('employment_change', 150000)

        signal, confidence = self._evaluate_macro(gdp_growth, inflation, interest_rate, employment)

        return AnalystResult(
            analyst_name='macro',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'GDP: {gdp_growth:.1f}%, CPI: {inflation:.1f}%, Rate: {interest_rate:.1f}%, Jobs: {employment}',
            data=macro_data
        )

    async def _fetch_macro_data(self, symbol: str) -> dict:
        # TODO: Replace with real macro data API (FRED, etc.)
        return {
            'gdp_growth': 2.3,
            'inflation_rate': 3.1,
            'interest_rate': 5.25,
            'employment_change': 187000,
            'pmi': 52.0,
            'consumer_confidence': 102.5,
        }

    def _evaluate_macro(self, gdp: float, inflation: float, rate: float, employment: int) -> tuple:
        if gdp > 2.5 and employment > 200000:
            return ('BUY', 0.65)
        elif gdp < 0.0 and inflation > 5.0:
            return ('SELL', 0.7)
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
