from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
import json

from config import settings
from db import call_stored_proc, call_stored_proc_table_vars
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

@router.get("/filtered")
def get_filtered_report(date_from: str, date_to: str, branches: str, draw_schedules: str, request: Request) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.report_filtered, "Filtered report stored procedure not configured")
    params = {
        "date_from": date_from,
        "date_to": date_to
    }
    branches_list = [(int(x),) for x in branches.split(",")]
    draw_schedules_list = [(int(x),) for x in draw_schedules.split(",")]
    print(f"branches={branches_list}, draw_schedules={draw_schedules_list}")
    table_params = [
        {
            "param": "branches",
            "type": "dbo.id_list",
            "columns": ["id"],
            "rows": branches_list
        },
        {
            "param": "draw_schedules",
            "type": "dbo.id_list",
            "columns": ["id"],
            "rows": draw_schedules_list
        }
    ]
    rows = call_stored_proc_table_vars(proc_name, params, table_params)
    return {"items": rows}
