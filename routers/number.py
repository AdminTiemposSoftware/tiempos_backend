from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from db import call_stored_proc

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
    proc_name = _get_proc(settings.number_by_draw_schedule, "Number by draw schedule stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("draw_schedule_id", draw_schedule_id)
    params.setdefault("branch_id", branch_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}