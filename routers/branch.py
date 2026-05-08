from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from db import call_stored_proc

router = APIRouter(prefix="/branch", tags=["branch"])


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


@router.get("")
def list_branch(request: Request) -> dict:
    # List branches using optional query params as filters.
    # Example query: /branch
    proc_name = _get_proc(settings.branch, "Branch stored procedure not configured")
    params = dict(request.query_params)
    params["banking_id"] = 1  # TODO : Temporary hardcoded filter for testing
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.get("/{branch_id}")
def get_branch(branch_id: str, request: Request) -> dict:
    # Get a single branch by id (merged with optional query params).
    # Example query: /branch/42
    proc_name = _get_proc(settings.branch_by_id, "Branch stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("branch_id", branch_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.post("")
def create_branch(request: Request, payload: dict[str, object] | None = Body(default=None)) -> dict:
    # Create a branch from body or query params.
    # Example JSON: {"name": "Sucursal Norte", "code": "SN01", "is_active": 1}
    proc_name = _get_proc(
        settings.branch_create,
        "Branch create stored procedure not configured",
    )
    params = _get_payload(request, payload)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.put("/{branch_id}")
def update_branch(
    branch_id: str,
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    # Update a branch by id using body or query params.
    # Example JSON: {"name": "Sucursal Norte 2", "is_active": 0}
    proc_name = _get_proc(
        settings.branch_update,
        "Branch update stored procedure not configured",
    )
    params = _get_payload(request, payload)
    params = {"branch_id": branch_id, **params}
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.delete("/{branch_id}")
def delete_branch(
    branch_id: str,
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    # Delete a branch by id. Optional payload/query params can be used for flags.
    # Example query: /branch/42?hard_delete=1
    proc_name = _get_proc(
        settings.branch_delete,
        "Branch delete stored procedure not configured",
    )
    params: dict[str, object] = {"branch_id": branch_id}
    if payload is not None:
        if not payload:
            raise HTTPException(status_code=400, detail="Payload cannot be empty")
        params.update(payload)
    else:
        params.update(dict(request.query_params))
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@router.get("/list")
def list_branch(request: Request) -> dict:
    proc_name = _get_proc(settings.branch_list, "Branch list stored procedure not configured")
    params = dict(request.query_params)
    rows = _call_proc(proc_name, params)
    return {"items": rows}