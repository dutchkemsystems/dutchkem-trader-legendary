import os
import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from api.routes import (
    market,
    analysts,
    consensus,
    scanner,
    legendary,
    trades,
    positions,
    auth,
    broker,
    backtesting,
    paper_trades,
    live_trading,
    emotion,
    defense,
    llm,
    scalping,
    scalper,
)
from api.websocket.handlers import (
    market_websocket,
    trades_websocket,
    consensus_websocket,
)

logger = logging.getLogger("dutchkem.api")

# ---------------------------------------------------------------------------
# Thread pool — increase to handle 12 parallel NIM LLM calls
# ---------------------------------------------------------------------------
_llm_executor = ThreadPoolExecutor(max_workers=16)

# ---------------------------------------------------------------------------
# Concurrency + Timeout middleware
# ---------------------------------------------------------------------------
_llm_semaphore = asyncio.Semaphore(3)  # max 3 concurrent LLM requests

# ---------------------------------------------------------------------------
# Auth Middleware — protect all routes except login, health, ws, metrics
# ---------------------------------------------------------------------------
from api.routes.auth import _verify_token

PUBLIC_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/health",
    "/metrics",
}


class AuthMiddleware(BaseHTTPMiddleware):
    """Check Bearer token on protected API routes."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        # Skip auth for public paths and WebSocket
        if path in PUBLIC_PATHS or path.startswith("/ws/"):
            return await call_next(request)
        # Skip auth for static files and docs
        if (
            path.startswith("/docs")
            or path.startswith("/openapi")
            or path.endswith((".js", ".css", ".ico"))
        ):
            return await call_next(request)
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            username = _verify_token(token)
            if username:
                request.state.user = username
                return await call_next(request)
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Cancel requests that exceed timeout to prevent event loop starvation."""

    DEFAULT_TIMEOUT = 30
    LLM_TIMEOUT = 90

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        timeout = (
            self.LLM_TIMEOUT
            if "consensus" in path or "scanner" in path
            else self.DEFAULT_TIMEOUT
        )
        try:
            response = await asyncio.wait_for(call_next(request), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            return JSONResponse(status_code=504, content={"error": "Request timeout"})
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})


app = FastAPI(title="Dutchkem Trader API", version="2.0.0")


@app.on_event("startup")
async def _startup_init():
    loop = asyncio.get_event_loop()
    loop.set_default_executor(_llm_executor)

    # Create default toggle_state.json if missing
    import json as _json
    from pathlib import Path

    state_file = (
        Path(__file__).resolve().parent.parent.parent
        / "trades_complete"
        / "toggle_state.json"
    )
    if not state_file.exists():
        state_file.parent.mkdir(exist_ok=True)
        default_state = {
            "main_engine_enabled": True,
            "mtf_cascading_scalper_enabled": True,
            "scalping_strategies": {
                "chiaroscuro": False,
                "london_ny_overlap": False,
                "checklist_5point": False,
                "autolot_20pip": False,
                "renko_20pip": False,
                "sniper": False,
                "ema_pullback": False,
                "session_breakout": False,
                "news_fade": False,
                "fvg_confluence": False,
                "smart_machine_ea": False,
                "gold_hedge_ea": False,
                "quantum_ai": True,
            },
        }
        state_file.write_text(_json.dumps(default_state, indent=2), encoding="utf-8")
        logger.info("Created default toggle_state.json")


# Auth middleware FIRST (before routes)
app.add_middleware(AuthMiddleware)
app.add_middleware(RequestTimeoutMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8888",
        "http://127.0.0.1:8888",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router, prefix="/api/v1/market", tags=["market"])
app.include_router(analysts.router, prefix="/api/v1/analysts", tags=["analysts"])
app.include_router(consensus.router, prefix="/api/v1/consensus", tags=["consensus"])
app.include_router(scanner.router, prefix="/api/v1/scanner", tags=["scanner"])
app.include_router(legendary.router, prefix="/api/v1/legendary", tags=["legendary"])
app.include_router(trades.router, prefix="/api/v1/trades", tags=["trades"])
app.include_router(positions.router, prefix="/api/v1/positions", tags=["positions"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(broker.router, prefix="/api/v1/broker", tags=["broker"])
app.include_router(backtesting.router, prefix="/api/v1/backtest", tags=["backtest"])
app.include_router(paper_trades.router, prefix="/api/v1", tags=["paper-trades"])
app.include_router(live_trading.router, prefix="/api/v1/live", tags=["live-trading"])
app.include_router(emotion.router, prefix="/api/v1/emotion", tags=["emotion"])
app.include_router(defense.router, prefix="/api/v1/defense", tags=["defense"])
app.include_router(llm.router, prefix="/api/v1/llm", tags=["llm"])
app.include_router(scalping.router, prefix="/api/v1/scalping", tags=["scalping"])
app.include_router(scalper.router, prefix="/api/v1/scalper", tags=["scalper"])


_start_time = time.time()


@app.get("/api/v1/health")
async def health_check():
    """Health check — no Django dependency."""
    return JSONResponse(
        content={
            "status": "healthy",
            "service": "dutchkem-trader-api",
            "uptime_seconds": round(time.time() - _start_time, 1),
            "checks": {"trading": "ready"},
        }
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        from fastapi.responses import Response

        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    except ImportError:
        return JSONResponse(
            content={"error": "prometheus_client not installed"}, status_code=503
        )


app.websocket("/ws/market/{symbol}")(market_websocket)
app.websocket("/ws/trades")(trades_websocket)
app.websocket("/ws/consensus")(consensus_websocket)
