import re
from typing import Optional


MARKET_PROMPT = """You are a technical market analyst. Analyze {symbol} on the {timeframe} timeframe.

Focus on these indicators: RSI, MACD, Bollinger Bands, ATR, Stochastic, Ichimoku, Fibonacci, VWAP.

Provide your analysis in EXACTLY this format:
SIGNAL: BUY|SELL|HOLD
CONFIDENCE: 0.0-1.0
REASONING: <your detailed reasoning including indicator values and trend analysis>"""

NEWS_PROMPT = """You are a news analyst. Analyze recent news and events for {symbol} on the {timeframe} timeframe.

Focus on: headline sentiment, market impact, event detection, earnings reports, central bank announcements, geopolitical events.

Provide your analysis in EXACTLY this format:
SIGNAL: BUY|SELL|HOLD
CONFIDENCE: 0.0-1.0
REASONING: <your detailed reasoning including key headlines and their market impact>"""

FUNDAMENTALS_PROMPT = """You are a fundamental analyst. Analyze the fundamentals of {symbol} on the {timeframe} timeframe.

Focus on: P/E ratio, P/B ratio, ROE, debt-to-equity, revenue growth, earnings quality, valuation metrics.

Provide your analysis in EXACTLY this format:
SIGNAL: BUY|SELL|HOLD
CONFIDENCE: 0.0-1.0
REASONING: <your detailed reasoning including key financial metrics and valuation assessment>"""

SENTIMENT_PROMPT = """You are a sentiment analyst. Analyze market sentiment for {symbol} on the {timeframe} timeframe.

Focus on: social media sentiment (Twitter/X, Reddit, Telegram), Fear & Greed Index, positioning data, COT report, retail vs institutional positioning.

Provide your analysis in EXACTLY this format:
SIGNAL: BUY|SELL|HOLD
CONFIDENCE: 0.0-1.0
REASONING: <your detailed reasoning including sentiment indicators and positioning analysis>"""

TECHNICAL_PROMPT = """You are a technical chart pattern analyst. Analyze chart patterns and technical structure for {symbol} on the {timeframe} timeframe.

Focus on: chart patterns (double bottom/top, head & shoulders, triangles, wedges), support/resistance levels, trendlines, candlestick patterns, price action.

Provide your analysis in EXACTLY this format:
SIGNAL: BUY|SELL|HOLD
CONFIDENCE: 0.0-1.0
REASONING: <your detailed reasoning including pattern identification and key price levels>"""

OPTIONS_PROMPT = """You are an options market analyst. Analyze the options market for {symbol} on the {timeframe} timeframe.

Focus on: implied volatility, put/call ratio, Greeks (delta, gamma, theta, vega), unusual options activity, skew, term structure, max pain.

Provide your analysis in EXACTLY this format:
SIGNAL: BUY|SELL|HOLD
CONFIDENCE: 0.0-1.0
REASONING: <your detailed reasoning including options metrics and volatility analysis>"""

ORDER_FLOW_PROMPT = """You are an order flow analyst. Analyze order flow and microstructure for {symbol} on the {timeframe} timeframe.

Focus on: microprice, bid/ask imbalance, cumulative volume delta (CVD), trade flow, volume profile, iceberg orders, sweep events.

Provide your analysis in EXACTLY this format:
SIGNAL: BUY|SELL|HOLD
CONFIDENCE: 0.0-1.0
REASONING: <your detailed reasoning including order flow metrics and liquidity analysis>"""

RISK_PROMPT = """You are a risk analyst. Analyze the risk profile for {symbol} on the {timeframe} timeframe.

Focus on: Value at Risk (VaR), maximum drawdown, Sharpe ratio, Sortino ratio, portfolio correlation, beta, tail risk, volatility regime.

Provide your analysis in EXACTLY this format:
SIGNAL: BUY|SELL|HOLD
CONFIDENCE: 0.0-1.0
REASONING: <your detailed reasoning including risk metrics and risk/reward assessment>"""

MACRO_PROMPT = """You are a macro analyst. Analyze the macroeconomic environment for {symbol} on the {timeframe} timeframe.

Focus on: GDP growth, inflation (CPI/PPI), interest rates, employment data, PMI, consumer confidence, central bank policy, currency strength, yield curves.

Provide your analysis in EXACTLY this format:
SIGNAL: BUY|SELL|HOLD
CONFIDENCE: 0.0-1.0
REASONING: <your detailed reasoning including macro indicators and economic outlook>"""

ON_CHAIN_PROMPT = """You are an on-chain analyst. Analyze blockchain and on-chain metrics for {symbol} on the {timeframe} timeframe.

Focus on: hash rate, wallet flow, exchange reserves, whale alerts, active addresses, NVT ratio, MVRV ratio, miner revenue, exchange inflow/outflow.

Provide your analysis in EXACTLY this format:
SIGNAL: BUY|SELL|HOLD
CONFIDENCE: 0.0-1.0
REASONING: <your detailed reasoning including on-chain metrics and blockchain analysis>"""

QUANT_PROMPT = """You are a quantitative analyst. Analyze quantitative signals for {symbol} on the {timeframe} timeframe.

Focus on: statistical arbitrage z-score, mean reversion signal, cointegration score, momentum score, half-life, Hurst exponent, factor loadings, pair correlations.

Provide your analysis in EXACTLY this format:
SIGNAL: BUY|SELL|HOLD
CONFIDENCE: 0.0-1.0
REASONING: <your detailed reasoning including quantitative metrics and statistical signals>"""

COMPLIANCE_PROMPT = """You are a compliance analyst. Analyze regulatory and compliance status for {symbol} on the {timeframe} timeframe.

Focus on: regulatory framework compliance, position limits, exposure limits, trading restrictions, sanctions screening, market abuse detection, reporting obligations.

Provide your analysis in EXACTLY this format:
SIGNAL: BUY|SELL|HOLD
CONFIDENCE: 0.0-1.0
REASONING: <your detailed reasoning including compliance status and regulatory assessment>"""


ANALYST_PROMPTS = {
    'market': MARKET_PROMPT,
    'news': NEWS_PROMPT,
    'fundamentals': FUNDAMENTALS_PROMPT,
    'sentiment': SENTIMENT_PROMPT,
    'technical': TECHNICAL_PROMPT,
    'options': OPTIONS_PROMPT,
    'order_flow': ORDER_FLOW_PROMPT,
    'risk': RISK_PROMPT,
    'macro': MACRO_PROMPT,
    'on_chain': ON_CHAIN_PROMPT,
    'quant': QUANT_PROMPT,
    'compliance': COMPLIANCE_PROMPT,
}


def parse_llm_response(text: str, llm_confidence: float = 0.7) -> dict:
    """Parse a structured LLM response into signal, confidence, and reasoning.

    Expects format:
        SIGNAL: BUY|SELL|HOLD
        CONFIDENCE: 0.0-1.0
        REASONING: <text>
    """
    signal = "HOLD"
    confidence = llm_confidence
    reasoning = text

    signal_match = re.search(r'SIGNAL:\s*(BUY|SELL|HOLD)', text, re.IGNORECASE)
    if signal_match:
        signal = signal_match.group(1).upper()

    conf_match = re.search(r'CONFIDENCE:\s*([\d.]+)', text, re.IGNORECASE)
    if conf_match:
        try:
            parsed_conf = float(conf_match.group(1))
            if 0.0 <= parsed_conf <= 1.0:
                confidence = parsed_conf
        except ValueError:
            pass

    reason_match = re.search(r'REASONING:\s*(.+)', text, re.IGNORECASE | re.DOTALL)
    if reason_match:
        reasoning = reason_match.group(1).strip()

    return {
        'signal': signal,
        'confidence': confidence,
        'reasoning': reasoning,
    }


def build_prompt(analyst_name: str, symbol: str, timeframe: str) -> Optional[str]:
    """Build a prompt for the given analyst, symbol, and timeframe."""
    template = ANALYST_PROMPTS.get(analyst_name)
    if template is None:
        return None
    return template.format(symbol=symbol, timeframe=timeframe)
