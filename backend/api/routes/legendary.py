from fastapi import APIRouter
import pandas as pd
import numpy as np
from apps.legendary.seykota import SeykotaTrendModule
from apps.legendary.pyramiding import PyramidingLogic
from apps.legendary.turtle_soup import TurtleSoupModule
from apps.legendary.soros import SorosAgent
from apps.legendary.buffett import BuffettAgent
from apps.legendary.druckenmiller import DruckenmillerAgent
from apps.legendary.tudor_jones import TudorJonesAgent
from apps.legendary.lynch import LynchAgent

router = APIRouter()

# Initialize all legendary agents
AGENTS = {
    "soros": SorosAgent(),
    "buffett": BuffettAgent(),
    "druckenmiller": DruckenmillerAgent(),
    "tudor_jones": TudorJonesAgent(),
    "lynch": LynchAgent(),
}

def _generate_market_data(n=200, base=100):
    """Generate simulated market data for analysis"""
    close = np.random.randn(n).cumsum() + base
    high = close + np.abs(np.random.randn(n)) * 0.5
    low = close - np.abs(np.random.randn(n)) * 0.5
    volume = np.random.randint(100000, 1000000, n).astype(float)
    return pd.DataFrame({'close': close, 'high': high, 'low': low, 'volume': volume})


# --- Original Legendary Modules ---

@router.get("/seykota/{symbol}")
async def get_seykota(symbol: str):
    module = SeykotaTrendModule()
    data = _generate_market_data(200)
    result = module.analyze_trend(data)
    return {"symbol": symbol, **result}


@router.get("/turtle-soup/{symbol}")
async def get_turtle_soup(symbol: str):
    module = TurtleSoupModule()
    data = _generate_market_data(50)
    result = module.detect_false_breakout(data)
    return {"symbol": symbol, "result": result}


@router.get("/pyramiding/{symbol}")
async def get_pyramiding(symbol: str):
    module = PyramidingLogic()
    return {"symbol": symbol, "entry_count": module.entry_count, "max_entries": module.max_entries}


# --- Persona Agent Endpoints ---

@router.get("/soros/{symbol}")
async def get_soros(symbol: str):
    agent = AGENTS["soros"]
    data = _generate_market_data(200)
    result = agent.analyze(data, symbol)
    return result


@router.get("/buffett/{symbol}")
async def get_buffett(symbol: str):
    agent = AGENTS["buffett"]
    data = _generate_market_data(200)
    result = agent.analyze(data, symbol)
    return result


@router.get("/druckenmiller/{symbol}")
async def get_druckenmiller(symbol: str):
    agent = AGENTS["druckenmiller"]
    data = _generate_market_data(200)
    result = agent.analyze(data, symbol)
    return result


@router.get("/tudor-jones/{symbol}")
async def get_tudor_jones(symbol: str):
    agent = AGENTS["tudor_jones"]
    data = _generate_market_data(200)
    result = agent.analyze(data, symbol)
    return result


@router.get("/lynch/{symbol}")
async def get_lynch(symbol: str):
    agent = AGENTS["lynch"]
    data = _generate_market_data(200)
    result = agent.analyze(data, symbol)
    return result


# --- Combined Analysis ---

@router.get("/analyze/{symbol}")
async def analyze_all_agents(symbol: str):
    """Run all 5 persona agents on a symbol and return combined results"""
    data = _generate_market_data(200)
    results = {}
    for name, agent in AGENTS.items():
        results[name] = agent.analyze(data, symbol)
    
    # Count votes
    buy_count = sum(1 for r in results.values() if r["signal"] == "BUY")
    sell_count = sum(1 for r in results.values() if r["signal"] == "SELL")
    hold_count = sum(1 for r in results.values() if r["signal"] == "HOLD")
    
    # Average confidence
    avg_confidence = sum(r["confidence"] for r in results.values()) / len(results)
    
    # Consensus signal
    if buy_count > sell_count and buy_count >= 3:
        consensus = "BUY"
    elif sell_count > buy_count and sell_count >= 3:
        consensus = "SELL"
    else:
        consensus = "HOLD"
    
    return {
        "symbol": symbol,
        "consensus": consensus,
        "buy_votes": buy_count,
        "sell_votes": sell_count,
        "hold_votes": hold_count,
        "avg_confidence": round(avg_confidence, 2),
        "agents": results,
    }


@router.get("/agents")
async def list_agents():
    """List all legendary persona agents"""
    return {
        "agents": [
            {
                "name": agent.name,
                "key": key,
                "philosophy": agent.philosophy,
                "specialties": agent.specialties,
                "risk_tolerance": agent.risk_tolerance,
            }
            for key, agent in AGENTS.items()
        ],
        "count": len(AGENTS),
    }
