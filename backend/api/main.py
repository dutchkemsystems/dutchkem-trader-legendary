from fastapi import FastAPI
from api.routes import market, analysts, consensus, scanner, legendary, trades, positions

app = FastAPI(title="Dutchkem Trader API", version="1.0.0")

app.include_router(market.router, prefix="/api/v1/market", tags=["market"])
app.include_router(analysts.router, prefix="/api/v1/analysts", tags=["analysts"])
app.include_router(consensus.router, prefix="/api/v1/consensus", tags=["consensus"])
app.include_router(scanner.router, prefix="/api/v1/scanner", tags=["scanner"])
app.include_router(legendary.router, prefix="/api/v1/legendary", tags=["legendary"])
app.include_router(trades.router, prefix="/api/v1/trades", tags=["trades"])
app.include_router(positions.router, prefix="/api/v1/positions", tags=["positions"])


@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "service": "dutchkem-trader-api"}
