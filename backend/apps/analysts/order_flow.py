from .base import BaseAnalyst, AnalystResult


class OrderFlowAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ['microprice', 'liquidity_imbalance', 'cvd', 'trade_flow']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt('order_flow', symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name='order_flow',
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed['signal'],
                confidence=parsed['confidence'],
                reasoning=parsed['reasoning'],
                data={'llm_model': response.model_used, 'data_source': 'llm'}
            )

        flow_data = await self._fetch_order_flow(symbol)
        microprice = self._calculate_microprice(flow_data)
        imbalance = self._calculate_imbalance(flow_data)

        signal, confidence = self._evaluate_flow(microprice, imbalance)

        return AnalystResult(
            analyst_name='order_flow',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'Microprice: {microprice:.5f}, Imbalance: {imbalance:.2f}',
            data=flow_data
        )

    async def _fetch_order_flow(self, symbol: str) -> dict:
        # TODO: Replace with real order book data
        return {
            'bid_volume': 15000,
            'ask_volume': 12000,
            'bid_price': 1.0890,
            'ask_price': 1.0892,
            'cvd': 500
        }

    def _calculate_microprice(self, data: dict) -> float:
        bid_vol = data.get('bid_volume', 1)
        ask_vol = data.get('ask_volume', 1)
        bid_price = data.get('bid_price', 0)
        ask_price = data.get('ask_price', 0)
        total = bid_vol + ask_vol
        return (bid_vol * ask_price + ask_vol * bid_price) / total if total > 0 else 0

    def _calculate_imbalance(self, data: dict) -> float:
        bid_vol = data.get('bid_volume', 1)
        ask_vol = data.get('ask_volume', 1)
        total = bid_vol + ask_vol
        return (bid_vol - ask_vol) / total if total > 0 else 0.0

    def _evaluate_flow(self, microprice: float, imbalance: float) -> tuple:
        if imbalance > 0.2:
            return ('BUY', min(0.6 + imbalance, 0.85))
        elif imbalance < -0.2:
            return ('SELL', min(0.6 + abs(imbalance), 0.85))
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
