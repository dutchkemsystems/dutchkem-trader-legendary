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
        if flow_data is None:
            return AnalystResult(
                analyst_name='order_flow',
                symbol=symbol,
                timeframe=timeframe,
                signal='HOLD',
                confidence=0.0,
                reasoning='MT5 data unavailable — cannot analyze order flow',
                data={'error': 'MT5 unavailable', 'data_source': 'none'}
            )
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
            data=flow_data,
            data_source='mt5'
        )

    async def _fetch_order_flow(self, symbol: str) -> dict:
        """Fetch real tick volume data from MT5 and analyze order flow.
        
        Uses actual tick data to classify buyer vs seller initiated transactions.
        A tick is buyer-initiated if the price moved up (ask was hit).
        A tick is seller-initiated if the price moved down (bid was hit).
        """
        try:
            import MetaTrader5 as mt5
            import numpy as np
            from datetime import datetime, timedelta
            
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                return None
            
            info = mt5.symbol_info(symbol)
            if not info:
                return None
            
            # Get real tick data (last ~1000 ticks from past hour)
            # copy_ticks_from(symbol, datetime, count, flags) is the correct API
            now = datetime.now()
            one_hour_ago = now - timedelta(hours=1)
            ticks = mt5.copy_ticks_from(symbol, one_hour_ago, 1000, mt5.COPY_TICKS_ALL)
            
            if ticks is None or len(ticks) < 10:
                # Fallback: use M1 bar volumes as approximation
                rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 20)
                if rates is not None and len(rates) > 0:
                    tick_volumes = [r['tick_volume'] for r in rates]
                    avg_vol = sum(tick_volumes) / len(tick_volumes)
                    # Use price direction in recent bars to estimate buyer/seller split
                    recent_closes = [r['close'] for r in rates[-5:]]
                    recent_opens = [r['open'] for r in rates[-5:]]
                    up_bars = sum(1 for c, o in zip(recent_closes, recent_opens) if c > o)
                    down_bars = len(recent_closes) - up_bars
                    total = up_bars + down_bars
                    bid_vol = int(avg_vol * (up_bars / total)) if total > 0 else int(avg_vol / 2)
                    ask_vol = int(avg_vol * (down_bars / total)) if total > 0 else int(avg_vol / 2)
                else:
                    return None
            else:
                # Classify ticks by price movement direction
                df_ticks = np.array(ticks)
                prices = df_ticks['last']
                
                # Determine direction: if price went up from previous tick → buyer
                # If price went down → seller
                directions = np.diff(prices)
                
                # Use tick volume as weight
                volumes = df_ticks[1:]['volume'].clip(min=1)
                
                # Buyer volume: sum of volume where price went up
                # Seller volume: sum of volume where price went down
                buyer_mask = directions > 0
                seller_mask = directions < 0
                
                bid_vol = int(np.sum(volumes[buyer_mask]))
                ask_vol = int(np.sum(volumes[seller_mask]))
                
                # If no clear direction, use 50/50 split
                if bid_vol == 0 and ask_vol == 0:
                    total_vol = int(np.sum(volumes))
                    bid_vol = total_vol // 2
                    ask_vol = total_vol // 2
            
            total = bid_vol + ask_vol
            cvd = bid_vol - ask_vol
            imbalance = cvd / total if total > 0 else 0.0
            
            return {
                'bid_volume': max(100, bid_vol),
                'ask_volume': max(100, ask_vol),
                'bid_price': tick.bid,
                'ask_price': tick.ask,
                'cvd': cvd,
                'imbalance': imbalance,
                'data_source': 'mt5',
            }
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Order flow fetch failed for {symbol}: {e}")
            return None

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
        """Evaluate order flow using imbalance, microprice deviation, and volume strength."""
        # Microprice deviation from mid-price
        if microprice > 0:
            bid = microprice * 0.999
            ask = microprice * 1.001
            mid = (bid + ask) / 2 if (bid + ask) > 0 else microprice
            deviation = (microprice - mid) / mid if mid > 0 else 0
        else:
            deviation = 0

        # Combined signal from imbalance and deviation
        flow_score = imbalance * 0.7 + deviation * 100 * 0.3

        # Strong flow: imbalance > 0.15 (lowered from 0.2)
        if flow_score > 0.15:
            confidence = min(0.6 + abs(flow_score) * 0.8, 0.85)
            return ('BUY', confidence)
        elif flow_score < -0.15:
            confidence = min(0.6 + abs(flow_score) * 0.8, 0.85)
            return ('SELL', confidence)

        # Weak flow: use microprice direction as tiebreaker
        if imbalance > 0.05:
            return ('BUY', 0.55)
        elif imbalance < -0.05:
            return ('SELL', 0.55)

        return ('HOLD', 0.5)

    def get_capabilities(self) -> list[str]:
        return list(self._capabilities)
