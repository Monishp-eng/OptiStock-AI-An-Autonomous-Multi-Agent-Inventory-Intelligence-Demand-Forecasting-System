"""
auth_router.py — Register on first run, login, and session endpoints
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.database import get_db
from src.auth import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


# ── GET /api/auth/status ─────────────────────────────────────────────────────
@router.get("/status")
def auth_status(db=Depends(get_db)):
    """
    Returns whether an owner account exists.
    Frontend uses this to route: no account → /setup, has account → /login.
    """
    count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return {"registered": count > 0}


# ── POST /api/auth/register ──────────────────────────────────────────────────
@router.post("/register")
def register(body: RegisterRequest, db=Depends(get_db)):
    """
    Register a new user account. Checks if username already exists.
    """
    # Check if this specific username already exists
    existing = db.execute(
        "SELECT id FROM users WHERE username = ?", (body.username.strip(),)
    ).fetchone()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken. Please choose a different username.",
        )

    if len(body.username.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be at least 3 characters.",
        )
    if len(body.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 6 characters.",
        )

    now = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?,?,?)",
        (body.username.strip(), hash_password(body.password), now),
    )
    db.commit()

    token = create_access_token({"sub": body.username.strip()})
    return {"access_token": token, "token_type": "bearer", "username": body.username.strip()}


# ── POST /api/auth/login ─────────────────────────────────────────────────────
@router.post("/login")
def login(body: LoginRequest, db=Depends(get_db)):
    """Validate credentials and return a JWT token."""
    user = db.execute(
        "SELECT * FROM users WHERE username = ?", (body.username.strip(),)
    ).fetchone()

    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    token = create_access_token({"sub": user["username"]})
    return {"access_token": token, "token_type": "bearer", "username": user["username"]}


# ── GET /api/auth/me ─────────────────────────────────────────────────────────
from src.auth import get_current_user

@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's info."""
    return {
        "id": current_user["id"],
        "username": current_user["username"],
        "created_at": current_user["created_at"],
    }
