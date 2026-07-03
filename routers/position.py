from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
import json

from config import settings
from db import call_stored_proc
from routers.auth import _require_auth

router = APIRouter(prefix="/position", tags=["position"])

def _get_proc(proc_name: str | None, detail: str) -> str:
    if not proc_name:
        raise HTTPException(status_code=500, detail=detail)
    return proc_name

def _call_proc(proc_name: str, params: dict[str, object] | None = None) -> list[dict]:
    try:
        return call_stored_proc(proc_name, params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Database error") from exc

def _get_payload(request: Request, payload: dict[str, object] | None) -> dict[str, object]:
    if payload is not None:
        if not payload:
            raise HTTPException(status_code=400, detail="Payload cannot be empty")
        return payload

    params = dict(request.query_params)
    if not params:
        raise HTTPException(status_code=400, detail="Payload is required")
    return params

@router.post("")
def create_position(
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    _require_auth(request)
    proc_name = _get_proc(
        settings.position_create, 
        "Position creation stored procedure not configured"
    )
    params = _get_payload(request, payload)
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@router.put("")
def update_position(
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    _require_auth(request)
    proc_name = _get_proc(
        settings.position_update, 
        "Position update stored procedure not configured"
    )
    params = _get_payload(request, payload)
    rows = _call_proc(proc_name, params)
    return {"items": rows}