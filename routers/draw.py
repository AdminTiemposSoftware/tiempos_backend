from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from db import call_stored_proc

router = APIRouter(prefix="/draw", tags=["draw"])
draw_schedule_router = APIRouter(prefix="/draw-schedule", tags=["draw_schedule"])
draw_day_router = APIRouter(prefix="/draw-day", tags=["draw_day"])
draw_schedule_branch_router = APIRouter(prefix="/draw-schedule-branch", tags=["draw_schedule_branch"])


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
def list_draw(request: Request) -> dict:
    proc_name = _get_proc(settings.draw, "Draw stored procedure not configured")
    params = dict(request.query_params)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.get("/{draw_id}")
def get_draw(draw_id: str, request: Request) -> dict:
    proc_name = _get_proc(settings.draw, "Draw stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("draw_id", draw_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.post("")
def create_draw(request: Request, payload: dict[str, object] | None = Body(default=None)) -> dict:
    proc_name = _get_proc(
        settings.draw_create,
        "Draw create stored procedure not configured",
    )
    params = _get_payload(request, payload)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.put("/{draw_id}")
def update_draw(
    draw_id: str,
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    proc_name = _get_proc(
        settings.draw_update,
        "Draw update stored procedure not configured",
    )
    params = _get_payload(request, payload)
    params = {"draw_id": draw_id, **params}
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.delete("/{draw_id}")
def delete_draw(
    draw_id: str,
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    proc_name = _get_proc(
        settings.draw_delete,
        "Draw delete stored procedure not configured",
    )
    params: dict[str, object] = {"draw_id": draw_id}
    if payload is not None:
        if not payload:
            raise HTTPException(status_code=400, detail="Payload cannot be empty")
        params.update(payload)
    else:
        params.update(dict(request.query_params))
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@draw_schedule_router.get("")
def list_draw_schedule(request: Request) -> dict:
    proc_name = _get_proc(
        settings.draw_schedule,
        "Draw schedule stored procedure not configured",
    )
    params = dict(request.query_params)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@draw_schedule_router.get("/{draw_schedule_id}")
def get_draw_schedule(draw_schedule_id: str, request: Request) -> dict:
    proc_name = _get_proc(
        settings.draw_schedule,
        "Draw schedule stored procedure not configured",
    )
    params = dict(request.query_params)
    params.setdefault("draw_schedule_id", draw_schedule_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@draw_schedule_router.post("")
def create_draw_schedule(
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    proc_name = _get_proc(
        settings.draw_schedule_create,
        "Draw schedule create stored procedure not configured",
    )
    params = _get_payload(request, payload)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@draw_schedule_router.put("/{draw_schedule_id}")
def update_draw_schedule(
    draw_schedule_id: str,
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    proc_name = _get_proc(
        settings.draw_schedule_update,
        "Draw schedule update stored procedure not configured",
    )
    params = _get_payload(request, payload)
    params = {"draw_schedule_id": draw_schedule_id, **params}
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@draw_schedule_router.delete("/{draw_schedule_id}")
def delete_draw_schedule(
    draw_schedule_id: str,
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    proc_name = _get_proc(
        settings.draw_schedule_delete,
        "Draw schedule delete stored procedure not configured",
    )
    params: dict[str, object] = {"draw_schedule_id": draw_schedule_id}
    if payload is not None:
        if not payload:
            raise HTTPException(status_code=400, detail="Payload cannot be empty")
        params.update(payload)
    else:
        params.update(dict(request.query_params))
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@draw_day_router.get("")
def list_draw_day(request: Request) -> dict:
    proc_name = _get_proc(
        settings.draw_day,
        "Draw day stored procedure not configured",
    )
    params = dict(request.query_params)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@draw_day_router.get("/{draw_day_id}")
def get_draw_day(draw_day_id: str, request: Request) -> dict:
    proc_name = _get_proc(
        settings.draw_day,
        "Draw day stored procedure not configured",
    )
    params = dict(request.query_params)
    params.setdefault("draw_day_id", draw_day_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@draw_day_router.post("")
def create_draw_day(
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    proc_name = _get_proc(
        settings.draw_day_create,
        "Draw day create stored procedure not configured",
    )
    params = _get_payload(request, payload)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@draw_day_router.put("/{draw_day_id}")
def update_draw_day(
    draw_day_id: str,
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    proc_name = _get_proc(
        settings.draw_day_update,
        "Draw day update stored procedure not configured",
    )
    params = _get_payload(request, payload)
    params = {"draw_day_id": draw_day_id, **params}
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@draw_day_router.delete("/{draw_day_id}")
def delete_draw_day(
    draw_day_id: str,
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    proc_name = _get_proc(
        settings.draw_day_delete,
        "Draw day delete stored procedure not configured",
    )
    params: dict[str, object] = {"draw_day_id": draw_day_id}
    if payload is not None:
        if not payload:
            raise HTTPException(status_code=400, detail="Payload cannot be empty")
        params.update(payload)
    else:
        params.update(dict(request.query_params))
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@draw_schedule_branch_router.post("")
def assign_schedule_to_branch(
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    proc_name = _get_proc(
        settings.draw_schedule_branch_create,
        "Draw schedule branch stored procedure not configured",
    )
    params = _get_payload(request, payload)
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@router.get("/by-branch/{branch_id}")
def get_draw_by_branch(branch_id: str, request: Request) -> dict:
    proc_name = _get_proc(
        settings.draw_by_branch,
        "Draw by branch stored procedure not configured",
    )
    params = dict(request.query_params)
    params.setdefault("branch_id", branch_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@router.get("/by-banking/{banking_id}")
def get_draw_by_banking(banking_id: str, request: Request) -> dict:
    proc_name = _get_proc(
        settings.draw_by_banking,
        "Draw by banking stored procedure not configured",
    )
    params = dict(request.query_params)
    params.setdefault("banking_id", banking_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}