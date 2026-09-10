from .base import BaseAnalyst, AnalystResult


class OnChainAnalyst(BaseAnalyst):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self._capabilities = ['blockchain_data', 'whale_tracking', 'exchange_flows']

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

        # On-chain data only relevant for crypto — N/A for forex
        if any(c in symbol.upper() for c in ['BTC', 'ETH', 'CRYPTO']):
            return AnalystResult(
                analyst_name='on_chain',
                symbol=symbol,
                timeframe=timeframe,
                signal='HOLD',
                confidence=0.0,
                reasoning='No on-chain API configured — requires Glassnode/CryptoQuant API',
                data={'error': 'no_onchain_api', 'data_source': 'none'}
            )
        else:
            return AnalystResult(
                analyst_name='on_chain',
                symbol=symbol,
                timeframe=timeframe,
                signal='HOLD',
                confidence=0.0,
                reasoning='On-chain data not applicable for forex pairs',
                data={'error': 'not_applicable', 'data_source': 'none'}
            )

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
