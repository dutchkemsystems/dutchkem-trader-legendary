from fastapi import APIRouter
from apps.analysts.market import MarketAnalyst
from apps.analysts.news import NewsAnalyst
from apps.analysts.fundamentals import FundamentalsAnalyst
from apps.analysts.sentiment import SentimentAnalyst
from apps.analysts.technical import TechnicalAnalyst
from apps.analysts.options import OptionsAnalyst
from apps.analysts.order_flow import OrderFlowAnalyst
from apps.analysts.risk import RiskAnalyst
from apps.analysts.macro import MacroAnalyst
from apps.analysts.on_chain import OnChainAnalyst
from apps.analysts.quant import QuantAnalyst
from apps.analysts.compliance import ComplianceAnalyst

router = APIRouter()

ANALYSTS = {
    "market": MarketAnalyst(),
    "news": NewsAnalyst(),
    "fundamentals": FundamentalsAnalyst(),
    "sentiment": SentimentAnalyst(),
    "technical": TechnicalAnalyst(),
    "options": OptionsAnalyst(),
    "order_flow": OrderFlowAnalyst(),
    "risk": RiskAnalyst(),
    "macro": MacroAnalyst(),
    "on_chain": OnChainAnalyst(),
    "quant": QuantAnalyst(),
    "compliance": ComplianceAnalyst(),
}


@router.get("/")
async def list_analysts():
    return {"analysts": list(ANALYSTS.keys()), "count": len(ANALYSTS)}


@router.get("/{analyst_name}")
async def get_analyst(analyst_name: str):
    if analyst_name not in ANALYSTS:
        return {"error": f"Analyst {analyst_name} not found"}
    analyst = ANALYSTS[analyst_name]
    return {"name": analyst_name, "capabilities": analyst.get_capabilities()}


@router.get("/{analyst_name}/analyze")
async def analyze(analyst_name: str, symbol: str, timeframe: str = "1H"):
    if analyst_name not in ANALYSTS:
        return {"error": f"Analyst {analyst_name} not found"}
    analyst = ANALYSTS[analyst_name]
    result = await analyst.analyze(symbol, timeframe)
    return {
        "analyst_name": result.analyst_name,
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "signal": result.signal,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "data": result.data
    }
