from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: str


# Single-user auth: hardcoded credentials for now
# TODO: Replace with real JWT in Sub-Project 2 (Order Execution)
VALID_USERNAME = "admin"
VALID_PASSWORD = "dutchkem"
MOCK_TOKEN = "dutchkem-jwt-token-v1"


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Authenticate user and return JWT token."""
    if req.username != VALID_USERNAME or req.password != VALID_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return LoginResponse(token=MOCK_TOKEN, user=req.username)


@router.get("/me")
async def get_current_user():
    """Get current authenticated user."""
    return {"user": VALID_USERNAME}
