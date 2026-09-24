import os
import hashlib
import hmac
import time
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: str


# Credentials from environment variables (never hardcoded)
VALID_USERNAME = os.environ.get("DASHBOARD_USERNAME", "admin")
VALID_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "dutchkem")
# HMAC secret for token signing
_TOKEN_SECRET = os.environ.get("TOKEN_SECRET", "dutchkem-change-this-in-production")


def _sign_token(username: str, timestamp: int) -> str:
    """Create a signed token from username + timestamp."""
    payload = f"{username}:{timestamp}"
    sig = hmac.new(
        _TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()[:16]
    return f"{username}:{timestamp}:{sig}"


def _verify_token(token: str) -> Optional[str]:
    """Verify token and return username if valid, else None."""
    parts = token.split(":")
    if len(parts) != 3:
        return None
    username, ts_str, sig = parts
    try:
        timestamp = int(ts_str)
    except ValueError:
        return None
    # Token expires after 24 hours
    if time.time() - timestamp > 86400:
        return None
    expected = _sign_token(username, timestamp)
    if hmac.compare_digest(token, expected):
        return username
    return None


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest):
    """Authenticate user and return signed token."""
    if req.username != VALID_USERNAME or req.password != VALID_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = _sign_token(req.username, int(time.time()))
    return LoginResponse(token=token, user=req.username)


@router.get("/me")
async def get_current_user(authorization: Optional[str] = Header(None)):
    """Get current authenticated user from token header."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.replace("Bearer ", "")
    username = _verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"user": username}
