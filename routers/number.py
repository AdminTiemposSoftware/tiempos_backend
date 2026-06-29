from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from db import call_stored_proc
from routers.auth import _require_auth

router = APIRouter(prefix="/number", tags=["number"])

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

@router.get("/by-draw-schedule/{draw_schedule_id}/{branch_id}")
def get_numbers_by_draw_schedule(draw_schedule_id: str, branch_id: str, request: Request) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.number_by_draw_schedule, "Number by draw schedule stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("draw_schedule_id", draw_schedule_id)
    params.setdefault("branch_id", branch_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@router.post("/prohibited")
def create_prohibited(request: Request, payload: dict[str, object]) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.prohibited_create, "Prohibited create stored procedure not configured")
    payload = _get_payload(request, payload)
    rows = _call_proc(proc_name, payload)
    return {"items": rows}

@router.put("/prohibited/{id}")
def update_prohibited(request: Request, id: str, payload: dict[str, object]) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.prohibited_update, "Prohibited update stored procedure not configured")
    payload = _get_payload(request, payload)
    payload["id"] = id
    _call_proc(proc_name, payload)
    return {"items": []}

@router.get("/prohibited/by-banking/{banking_id}")
def get_prohibited_by_banking_id(banking_id: str, request: Request) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.prohibited_by_banking_id, "Prohibited by banking ID stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("banking_id", banking_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@router.get("/prohibited/by-branch/{branch_id}")
def get_prohibited_by_branch_id(branch_id: str, request: Request) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.prohibited_by_branch_id, "Prohibited by branch ID stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("branch_id", branch_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@router.delete("/prohibited/{banking_id}/{number_id}")
def delete_prohibited(request: Request, banking_id: str, number_id: str) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.prohibited_delete, "Prohibited delete stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("banking_id", banking_id)
    params.setdefault("number_id", number_id)
    _call_proc(proc_name, params)
    return {"items": []}