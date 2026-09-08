"""
Live Paper Trading Engine
========================
Runs the full V5 intelligence pipeline on real market data:
1. Fetch real candles from AKShare
2. Run 12 analysts in parallel (LLM-powered)
3. 7-gate consensus validation
4. Bull vs Bear debate
5. Memory context lookup
6. ML prediction
7. Kelly position sizing
8. Generate trade decision
9. Log paper trade
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows encoding for print
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

import django
django.setup()

from apps.consensus.engine import ConsensusEngine
from apps.consensus.gates import ConsensusGates
from apps.consensus.black_scholes import BlackScholesEngine
from apps.consensus.regime import MarketRegimeDetector
from apps.debate.engine import DebateEngine
from apps.memory.situation_memory import FinancialSituationMemory
from apps.ml.predictor import MLPredictor
from apps.vision import ChartAnalyzer
from apps.llm.client import LLMClient
from data.manager import MarketDataManager
from execution.kelly_sizer import KellySizer
from execution.risk_config import RiskConfig
from execution.circuit_breaker import CircuitBreaker

# All 12 analysts
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


# ─── Config ──────────────────────────────────────────────────
WATCHLIST = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]
TIMEFRAME = "1H"
CYCLE_INTERVAL = 300  # 5 minutes between cycles
PAPER_TRADES_DIR = Path("paper_trades")


def build_system():
    """Build the full V5 intelligence system."""
    data_manager = MarketDataManager()
    chart_analyzer = ChartAnalyzer()
    llm_client = LLMClient()

    # 12 analysts
    analysts = [
        MarketAnalyst(),
        NewsAnalyst(),
        FundamentalsAnalyst(),
        SentimentAnalyst(),
        TechnicalAnalyst(chart_analyzer=chart_analyzer),
        OptionsAnalyst(),
        OrderFlowAnalyst(),
        RiskAnalyst(),
        MacroAnalyst(),
        OnChainAnalyst(),
        QuantAnalyst(),
        ComplianceAnalyst(),
    ]

    # V5 components
    ml_predictor = MLPredictor(model_type="xgboost")
    debate_engine = DebateEngine(max_rounds=1, llm_client=llm_client)
    memory = FinancialSituationMemory()
    gates = ConsensusGates(ml_predictor=ml_predictor)
    regime_detector = MarketRegimeDetector()
    black_scholes = BlackScholesEngine()
    kelly = KellySizer()
    risk_config = RiskConfig()
    circuit_breaker = CircuitBreaker()

    # Consensus engine
    engine = ConsensusEngine(
        analysts=analysts,
        ml_predictor=ml_predictor,
        debate_engine=debate_engine,
        memory=memory,
    )

    return {
        "data_manager": data_manager,
        "engine": engine,
        "gates": gates,
        "regime_detector": regime_detector,
        "black_scholes": black_scholes,
        "kelly": kelly,
        "risk_config": risk_config,
        "circuit_breaker": circuit_breaker,
        "llm_client": llm_client,
    }


async def analyze_symbol(system, symbol, timeframe):
    """Run full analysis on a single symbol."""
    start = time.time()

    # 1. Run consensus (12 analysts parallel + debate + memory)
    engine = system["engine"]
    result = await engine.evaluate(symbol, timeframe, use_debate=True, use_memory=True)

    # 2. Run 7 gates
    gates = system["gates"]
    regime_detector = system["regime_detector"]
    black_scholes = system["black_scholes"]
    gates.regime_detector = regime_detector
    gates.black_scholes = black_scholes

    gate_result = gates.evaluate_all(
        consensus={"agreement_pct": result.get("agreement_pct", 0)},
        analyst_results=[],
        p_up=0.5,
        market_price=0.5,
        risk_status={"max_positions": 10, "current_positions": 0},
    )

    # 3. Kelly sizing (if trade allowed)
    kelly_size = None
    if gate_result["trade_allowed"] and result["action"] != "HOLD":
        kelly = system["kelly"]
        kelly_size = kelly.calculate(
            win_rate=0.55,
            win_loss_ratio=1.5,
            account_balance=10000,
        )

    elapsed = time.time() - start

    return {
        "symbol": symbol,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "action": result["action"],
        "confidence": round(result["confidence"], 3),
        "agreement_pct": round(result.get("agreement_pct", 0), 3),
        "reason": result.get("reason", ""),
        "gates": gate_result,
        "debate": result.get("debate", {}),
        "similar_situations": len(result.get("similar_situations", [])),
        "kelly_size": kelly_size,
        "vote_counts": result.get("votes", {}),
    }


def format_decision(analysis):
    """Format analysis into a readable decision."""
    action = analysis["action"]
    confidence = analysis["confidence"]
    gates = analysis["gates"]
    debate = analysis.get("debate", {})

    # Color coding
    if action == "BUY":
        marker = "[BUY]"
    elif action == "SELL":
        marker = "[SELL]"
    else:
        marker = "[HOLD]"

    lines = [
        f"{marker} {analysis['symbol']} | {action} | Confidence: {confidence:.1%}",
        f"   Agreement: {analysis['agreement_pct']:.1%} | Gates: {gates['passed_count']}/{gates['total_gates']}",
    ]

    if debate and debate.get("winner"):
        winner = debate["winner"]
        bull = debate.get("bull_confidence", 0)
        bear = debate.get("bear_confidence", 0)
        lines.append(f"   Debate: {winner} (Bull: {bull:.1%} | Bear: {bear:.1%})")

    if analysis["similar_situations"] > 0:
        lines.append(f"   Memory: {analysis['similar_situations']} similar situations found")

    if analysis["kelly_size"]:
        lines.append(f"   Kelly Size: {analysis['kelly_size']:.1%} of account")

    if not gates["trade_allowed"]:
        # Find which gates failed
        failed = [k for k, v in gates["gates"].items() if not v["passed"]]
        lines.append(f"   BLOCKED by: {', '.join(failed)}")

    return "\n".join(lines)


def save_paper_trade(analysis):
    """Save paper trade to file."""
    PAPER_TRADES_DIR.mkdir(exist_ok=True)
    filename = PAPER_TRADES_DIR / f"trades_{datetime.now().strftime('%Y%m%d')}.jsonl"
    with open(filename, "a") as f:
        f.write(json.dumps(analysis) + "\n")


async def run_cycle(system, cycle_num):
    """Run one full analysis cycle."""
    print(f"\n{'='*60}")
    print(f"  CYCLE {cycle_num} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    results = []
    for symbol in WATCHLIST:
        try:
            analysis = await analyze_symbol(system, symbol, TIMEFRAME)
            results.append(analysis)
            print(format_decision(analysis))
            save_paper_trade(analysis)
        except Exception as e:
            print(f"  ERROR {symbol}: {e}")
            results.append({"symbol": symbol, "error": str(e)})

    # Summary
    actions = [r.get("action", "ERROR") for r in results if "action" in r]
    buys = actions.count("BUY")
    sells = actions.count("SELL")
    holds = actions.count("HOLD")
    print(f"\n  Summary: {buys} BUY | {sells} SELL | {holds} HOLD out of {len(WATCHLIST)} symbols")

    return results


async def main():
    """Main paper trading loop."""
    print("\n" + "="*60)
    print("  DUTCHKEM TRADER - LIVE PAPER TRADING")
    print("  V5 Intelligence Engine")
    print("="*60)

    # Build system
    print("\nBuilding V5 intelligence system...")
    system = build_system()
    print(f"  Analysts: 12 (parallel via asyncio.gather)")
    print(f"  LLM: {system['llm_client'].provider_status['primary']}")
    print(f"  ML: XGBoost predictor")
    print(f"  Gates: 7 mandatory gates")
    print(f"  Debate: Bull vs Bear (1 round)")
    print(f"  Memory: BM25 situational")
    print(f"  Watchlist: {', '.join(WATCHLIST)}")
    print(f"  Timeframe: {TIMEFRAME}")
    print(f"  Cycle interval: {CYCLE_INTERVAL}s")

    # Run first cycle immediately
    cycle = 1
    await run_cycle(system, cycle)

    # Continue looping
    print(f"\n  Next cycle in {CYCLE_INTERVAL}s (Ctrl+C to stop)...")
    while True:
        try:
            await asyncio.sleep(CYCLE_INTERVAL)
            cycle += 1
            await run_cycle(system, cycle)
        except KeyboardInterrupt:
            print("\n\n  Paper trading stopped.")
            break


if __name__ == "__main__":
    asyncio.run(main())
