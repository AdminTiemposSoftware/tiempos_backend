from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from config import settings
from fastapi import APIRouter, Body, HTTPException, Request
from routers.auth import _require_auth
from sqlalchemy.exc import SQLAlchemyError

from db import call_stored_proc, call_stored_proc_table_vars, call_stored_proc_table_var

router = APIRouter(prefix="/amount", tags=["amount"])

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

@router.get("/{branch_id}")
def get_amounts(request: Request, branch_id: int) -> dict:
    _require_auth(request)

    proc_name = _get_proc(settings.amount_name_by_branch or settings.amount_name, "stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("branch_id", branch_id)
    rows = _call_proc(proc_name, params)

    return {"items": rows}

@router.post("/")
def create_amount(request: Request, payload: dict[str, object] ) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.amount_name_create, "stored procedure not configured")
    rows = _call_proc(proc_name, payload)
    return {"items": rows}


@router.put("/")
def update_amount(request: Request, payload: dict[str, object]) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.amount_name_update, "stored procedure not configured")
    rows = _call_proc(proc_name, payload)
    return {"items": rows}


@router.delete("/{amount_name_id}")
def delete_amount(request: Request, amount_name_id: str) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.amount_name_delete, "stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("id", amount_name_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}
