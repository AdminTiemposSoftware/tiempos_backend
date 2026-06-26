from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from db import call_stored_proc
from routers.auth import _require_auth

router = APIRouter(prefix="/report", tags=["report"])

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
    
@router.get("/today/{banking_id}")
def get_report_of_today(banking_id: str, request: Request) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.report_today, "Report of today stored procedure not configured")
    params = {"banking_id": banking_id}
    rows = _call_proc(proc_name, params)
    return {"items": rows}
