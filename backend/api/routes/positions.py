from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_positions():
    # Placeholder: will query database
    return {"positions": [], "count": 0}


@router.get("/{position_id}")
async def get_position(position_id: str):
    # Placeholder: will query database
    return {"id": position_id, "unrealized_pnl": 0}
