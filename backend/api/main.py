import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import time
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from api.routes import market, analysts, consensus, scanner, legendary, trades, positions, auth, broker, backtesting
from api.websocket.handlers import market_websocket, trades_websocket, consensus_websocket

app = FastAPI(title="Dutchkem Trader API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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


_start_time = time.time()


@app.get("/api/v1/health")
def health_check():
    checks = {}
    status = "healthy"

    # Database check
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        status = "degraded"

    # Redis check
    try:
        from django.core.cache import cache
        cache.set("_healthcheck", "ok", 10)
        checks["redis"] = "ok" if cache.get("_healthcheck") == "ok" else "error"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        status = "degraded"

    # Trading readiness
    checks["trading"] = "ready"

    code = 200 if status == "healthy" else 503
    return JSONResponse(
        content={
            "status": status,
            "service": "dutchkem-trader-api",
            "uptime_seconds": round(time.time() - _start_time, 1),
            "checks": checks,
        },
        status_code=code,
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi.responses import Response
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.websocket("/ws/market/{symbol}")(market_websocket)
app.websocket("/ws/trades")(trades_websocket)
app.websocket("/ws/consensus")(consensus_websocket)
