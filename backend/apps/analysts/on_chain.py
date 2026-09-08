from .base import BaseAnalyst, AnalystResult


class OnChainAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ['hash_rate', 'wallet_flow', 'exchange_reserves', 'whale_alerts']

    async def analyze(self, symbol: str, timeframe: str) -> AnalystResult:
        if self.llm_client:
            from .prompts import build_prompt, parse_llm_response
            prompt = build_prompt('on_chain', symbol, timeframe)
            response = self.llm_client.analyze(prompt)
            parsed = parse_llm_response(response.text, response.confidence)
            return AnalystResult(
                analyst_name='on_chain',
                symbol=symbol,
                timeframe=timeframe,
                signal=parsed['signal'],
                confidence=parsed['confidence'],
                reasoning=parsed['reasoning'],
                data={'llm_model': response.model_used, 'data_source': 'llm'}
            )

        on_chain_data = await self._fetch_on_chain_data(symbol)
        hash_rate = on_chain_data.get('hash_rate', 0)
        wallet_flow = on_chain_data.get('wallet_flow', 0)
        exchange_reserves = on_chain_data.get('exchange_reserves', 0)
        whale_alerts = on_chain_data.get('whale_alerts', [])

        signal, confidence = self._evaluate_on_chain(hash_rate, wallet_flow, exchange_reserves, whale_alerts)

        return AnalystResult(
            analyst_name='on_chain',
            symbol=symbol,
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            reasoning=f'HashRate: {hash_rate}, Flow: {wallet_flow}, Reserves: {exchange_reserves}, Whales: {len(whale_alerts)}',
            data=on_chain_data
        )

    async def _fetch_on_chain_data(self, symbol: str) -> dict:
        # TODO: Replace with real on-chain data API (Glassnode, etc.)
        return {
            'hash_rate': 350e18,
            'wallet_flow': 1250,
            'exchange_reserves': -500,
            'whale_alerts': [
                {'amount': 5000, 'direction': 'inflow'},
            ],
            'active_addresses': 900000,
            'nvt_ratio': 85.0,
        }

    def _evaluate_on_chain(self, hash_rate: float, wallet_flow: int, exchange_reserves: int, whale_alerts: list) -> tuple:
        outflow = sum(1 for a in whale_alerts if a.get('direction') == 'outflow')
        inflow = sum(1 for a in whale_alerts if a.get('direction') == 'inflow')

        if exchange_reserves < 0 and outflow > inflow:
            return ('BUY', 0.7)
        elif exchange_reserves > 0 and inflow > outflow:
            return ('SELL', 0.7)
        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
