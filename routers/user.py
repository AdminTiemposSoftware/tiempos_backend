from argon2 import PasswordHasher
from argon2.exceptions import HashingError
from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from db import call_stored_proc

router = APIRouter(prefix="/user", tags=["user"])

_password_hasher = PasswordHasher()


def _get_proc(proc_name: str | None, detail: str) -> str:
    # Resolve stored procedure name or fail fast with a config error.
    if not proc_name:
        raise HTTPException(status_code=500, detail=detail)
    return proc_name


def _call_proc(proc_name: str, params: dict[str, object] | None = None) -> list[dict]:
    # Centralize DB error handling for stored procedure calls.
    try:
        return call_stored_proc(proc_name, params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Database error") from exc


def _get_payload(request: Request, payload: dict[str, object] | None) -> dict[str, object]:
    # Allow body payloads or query params, but require at least one value.
    if payload is not None:
        if not payload:
            raise HTTPException(status_code=400, detail="Payload cannot be empty")
        return payload

    params = dict(request.query_params)
    if not params:
        raise HTTPException(status_code=400, detail="Payload is required")
    return params


def _apply_password_hash(params: dict[str, object]) -> dict[str, object]:
    # Hash plaintext password into password_hash before persistence.
    password = params.pop("password", None)
    if password is None:
        return params
    if not isinstance(password, str) or not password:
        raise HTTPException(status_code=400, detail="Password must be a non-empty string")
    try:
        params["password_hash"] = _password_hasher.hash(password)
    except HashingError as exc:
        raise HTTPException(status_code=500, detail="Password hashing failed") from exc
    return params


@router.get("")
def list_user(request: Request) -> dict:
    # List users using optional query params as filters.
    # Example query: /user?enabled=1
    proc_name = _get_proc(settings.user, "User stored procedure not configured")
    params = dict(request.query_params)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.get("/{user_id}")
def get_user(user_id: str, request: Request) -> dict:
    # Get a single user by id (merged with optional query params).
    # Example query: /user/42
    proc_name = _get_proc(settings.user, "User stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("user_id", user_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.post("")
def create_user(request: Request, payload: dict[str, object] | None = Body(default=None)) -> dict:
    proc_name = _get_proc(
        settings.user_create,
        "User create stored procedure not configured",
    )
    params = _apply_password_hash(_get_payload(request, payload))
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.put("/{user_id}")
def update_user(
    user_id: str,
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    # Update a user by id using body or query params.
    # Example JSON: {"name": "Admin 2", "phone": "5559999", "role": "manager", "password": "new-secret"}
    proc_name = _get_proc(
        settings.user_update,
        "User update stored procedure not configured",
    )
    params = _apply_password_hash(_get_payload(request, payload))
    params = {"user_id": user_id, **params}
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    # Delete a user by id. Optional payload/query params can be used for flags.
    # Example query: /user/42?hard_delete=1
    proc_name = _get_proc(
        settings.user_delete,
        "User delete stored procedure not configured",
    )
    params: dict[str, object] = {"user_id": user_id}
    if payload is not None:
        if not payload:
            raise HTTPException(status_code=400, detail="Payload cannot be empty")
        params.update(payload)
    else:
        params.update(dict(request.query_params))
    rows = _call_proc(proc_name, params)
    return {"items": rows}
