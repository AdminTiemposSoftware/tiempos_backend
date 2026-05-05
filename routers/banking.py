from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from db import call_stored_proc

router = APIRouter(prefix="/banking", tags=["banking"])


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


@router.get("")
def list_banking(request: Request) -> dict:
    proc_name = _get_proc(settings.banking, "Banking stored procedure not configured")
    params = dict(request.query_params)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.get("/{banking_id}")
def get_banking(banking_id: str, request: Request) -> dict:
    proc_name = _get_proc(settings.banking, "Banking stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("banking_id", banking_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.post("")
def create_banking(request: Request, payload: dict[str, object] | None = Body(default=None)) -> dict:
    proc_name = _get_proc(
        settings.banking_create,
        "Banking create stored procedure not configured",
    )
    params = _get_payload(request, payload)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.put("/{banking_id}")
def update_banking(
    banking_id: str,
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    proc_name = _get_proc(
        settings.banking_update,
        "Banking update stored procedure not configured",
    )
    params = _get_payload(request, payload)
    params = {"banking_id": banking_id, **params}
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.delete("/{banking_id}")
def delete_banking(
    banking_id: str,
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    proc_name = _get_proc(
        settings.banking_delete,
        "Banking delete stored procedure not configured",
    )
    params: dict[str, object] = {"banking_id": banking_id}
    if payload is not None:
        if not payload:
            raise HTTPException(status_code=400, detail="Payload cannot be empty")
        params.update(payload)
    else:
        params.update(dict(request.query_params))
    rows = _call_proc(proc_name, params)
    return {"items": rows}
