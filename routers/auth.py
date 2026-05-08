import base64
import hashlib
import hmac
import json
import time
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Body, HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from db import call_stored_proc

router = APIRouter(prefix="/auth", tags=["auth"])

_password_hasher = PasswordHasher()


def _get_proc(proc_name: str | None, detail: str) -> str:
    if not proc_name:
        raise HTTPException(status_code=500, detail=detail)
    return proc_name


def _call_proc(proc_name: str, params: dict[str, object]) -> list[dict]:
    try:
        return call_stored_proc(proc_name, params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Database error") from exc


def _get_secret() -> str:
    secret = settings.auth_secret.strip()
    if not secret:
        raise HTTPException(status_code=500, detail="Auth secret not configured")
    return secret


def _b64encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _b64decode(payload: str) -> bytes:
    padding = "=" * (-len(payload) % 4)
    return base64.urlsafe_b64decode(payload + padding)


def _sign(data: str, secret: str) -> str:
    return hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()


def _create_token(user: dict[str, Any]) -> str:
    secret = _get_secret()
    payload = {
        "sub": str(user["id"]),
        "role": str(user.get("role", "user")),
        "username": str(user.get("username", "")),
        "exp": int(time.time()) + settings.auth_token_ttl_seconds,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = _sign(encoded, secret)
    return f"{encoded}.{signature}"


def _verify_token(token: str) -> dict[str, Any] | None:
    secret = _get_secret()
    if "." not in token:
        return None
    encoded, signature = token.split(".", 1)
    if not hmac.compare_digest(signature, _sign(encoded, secret)):
        return None
    try:
        payload = json.loads(_b64decode(encoded))
    except (json.JSONDecodeError, ValueError):
        return None
    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        return None
    return payload


@router.post("/login")
async def login(
    response: Response,
    payload: dict[str, object] = Body(...),
) -> dict:
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")

    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    proc_name = _get_proc(settings.auth_user, "Auth stored procedure not configured")
    rows = _call_proc(proc_name, {"username": username})
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = rows[0]
    if not user.get("enabled", True):
        raise HTTPException(status_code=403, detail="User is disabled")

    password_hash = user.get("password_hash")
    if not isinstance(password_hash, str):
        raise HTTPException(status_code=500, detail="Password hash not available")

    try:
        _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = _create_token(user)

    print(token)
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
    )

    return {
        "token": token,
        "user": {
            "id": str(user.get("id")),
            "role": str(user.get("role", "user")),
            "username": str(user.get("username", "")),
        },
    }


@router.get("/me")
async def me(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    token = ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get(settings.auth_cookie_name, "")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = _verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {
        "user": {
            "id": str(payload.get("sub", "")),
            "role": str(payload.get("role", "user")),
            "username": str(payload.get("username", "")),
        }
    }


@router.post("/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(settings.auth_cookie_name, path="/")
    return {"ok": True}
