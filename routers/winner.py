from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
import json

from config import settings
from db import call_stored_proc
from routers.auth import _require_auth

router = APIRouter(prefix="/winner", tags=["winner"])

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

@router.get("/by-banking/{banking_id}/{date}")
def get_winner(banking_id: str, date: str, request: Request) -> dict:
    _require_auth(request)
    proc_name = _get_proc(
        settings.winner_by_banking_id, 
        "Winner stored procedure not configured"
    )
    params = dict(request.query_params)
    params.setdefault("banking_id", banking_id)
    params.setdefault("date", date)
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@router.get("/by-branch/{branch_id}/{date}")
def get_winner(branch_id: str, date: str, request: Request) -> dict:
    _require_auth(request)
    proc_name = _get_proc(
        settings.winner_by_branch_id, 
        "Winner stored procedure not configured"
    )
    params = dict(request.query_params)
    params.setdefault("branch_id", branch_id)
    params.setdefault("date", date)
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@router.post("")
def create_winner(
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    _require_auth(request)
    proc_name = _get_proc(
        settings.winner_create, 
        "Winner creation stored procedure not configured"
    )
    params = _get_payload(request, payload)
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@router.post("/pay")
def pay_winner(
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    _require_auth(request)
    
    proc_name = _get_proc(
        settings.winner_pay, 
        "Winner payment stored procedure not configured"
    )
    params = _get_payload(request, payload)
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@router.get("/by-serial/{branch_id}/{serial}")
def get_winner_by_serial(request: Request, branch_id: int, serial: str) -> dict:
    _require_auth(request)
    proc_name = settings.winner_by_serial
    if not proc_name:
        raise HTTPException(status_code=500, detail="Tickets by serial stored procedure not configured")
    
    try:
        results = call_stored_proc(
            proc_name,
            {"serial": serial, "branch_id": branch_id},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Database error") from exc

    if not results:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"items": results}

