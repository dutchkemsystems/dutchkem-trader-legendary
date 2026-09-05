from fastapi import APIRouter
import pandas as pd
import numpy as np
from apps.legendary.seykota import SeykotaTrendModule
from apps.legendary.pyramiding import PyramidingLogic
from apps.legendary.turtle_soup import TurtleSoupModule

router = APIRouter()


@router.get("/seykota/{symbol}")
async def get_seykota(symbol: str):
    module = SeykotaTrendModule()
    data = pd.DataFrame({
        'close': np.random.randn(200).cumsum() + 100,
        'high': np.random.randn(200).cumsum() + 101,
        'low': np.random.randn(200).cumsum() + 99
    })
    result = module.analyze_trend(data)
    return {"symbol": symbol, **result}


@router.get("/turtle-soup/{symbol}")
async def get_turtle_soup(symbol: str):
    module = TurtleSoupModule()
    data = pd.DataFrame({
        'close': np.random.randn(50).cumsum() + 100,
        'high': np.random.randn(50).cumsum() + 101,
        'low': np.random.randn(50).cumsum() + 99
    })
    result = module.detect_false_breakout(data)
    return {"symbol": symbol, "result": result}


@router.get("/pyramiding/{symbol}")
async def get_pyramiding(symbol: str):
    module = PyramidingLogic()
    return {"symbol": symbol, "entry_count": module.entry_count, "max_entries": module.max_entries}
