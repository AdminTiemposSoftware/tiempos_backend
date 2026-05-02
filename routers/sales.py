from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from db import call_stored_proc

router = APIRouter(prefix="/sales", tags=["sales"])


@router.get("")
def list_sales(request: Request) -> dict:
    proc_name = settings.sales_proc
    if not proc_name:
        raise HTTPException(status_code=500, detail="Sales stored procedure not configured")

    try:
        params = dict(request.query_params)
        rows = call_stored_proc(proc_name, params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Database error") from exc

    return {"items": rows}
