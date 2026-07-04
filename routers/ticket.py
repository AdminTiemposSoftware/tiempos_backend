from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from routers.auth import _require_auth

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from db import call_stored_proc, call_stored_proc_multi, call_stored_proc_table_var

from routers.auth import _require_auth

router = APIRouter(prefix="/ticket", tags=["ticket"])


def _to_decimal_str(value: object, field_name: str) -> str:
    try:
        normalized = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return format(normalized, "f")
    except (InvalidOperation, TypeError):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a decimal value")


def _generate_serial(draw_schedule_id: object, branch_id: object) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%y%m%d%H%M%S")
    branch_part = str(branch_id or 0).zfill(2)[-2:]
    schedule_part = str(draw_schedule_id or 0).zfill(2)[-2:]
    serial = f"{timestamp}{branch_part}{schedule_part}"
    if len(serial) > 30:
        raise HTTPException(status_code=500, detail="Generated ticket serial exceeds database limit")
    return serial

@router.get("")
def list_tickets(request: Request) -> dict:
    proc_name = settings.tickets_proc
    if not proc_name:
        raise HTTPException(status_code=500, detail="Tickets stored procedure not configured")

    try:
        params = dict(request.query_params)
        rows = call_stored_proc(proc_name, params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Database error") from exc

    return {"items": rows}

@router.post("")
def create_ticket(request: Request, payload: dict[str, object]) -> dict:
    _require_auth(request)
    proc_name = settings.ticket_create
    if not proc_name:
        raise HTTPException(status_code=500, detail="Tickets create stored procedure not configured")

    details = payload.get("details")
    if not isinstance(details, list) or not details:
        raise HTTPException(status_code=400, detail="details must be a non-empty list")

    detail_rows = []
    for detail in details:
        detail_rows.append(
            (
                detail["number"],
                _to_decimal_str(detail.get("amount"), "details.amount"),
                detail["is_reventado"],
                detail["is_megareventado"],
            )
        )

    # Calculate total amount from details
    try:
        total_amount = sum(Decimal(str(detail.get("amount", 0))) for detail in details)
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Each details.amount must be a valid decimal value")

    printed_at = datetime.now(timezone.utc)

    params = {
        "draw_schedule_id": payload.get("draw_schedule_id"),
        "branch_id": payload.get("branch_id"),
        "serial": _generate_serial(payload.get("draw_schedule_id"), payload.get("branch_id")),
        "amount": _to_decimal_str(total_amount, "amount"),
        "printed_at": printed_at.isoformat(),
    }

    rows = call_stored_proc_table_var(
        proc_name,
        params=params,
        table_param="details",
        table_type="dbo.ticket_detail_list",
        table_columns=["number", "amount", "is_reventado", "is_megareventado"],
        table_rows=detail_rows,
    )
    return {"items": rows}

@router.get("/by-schedule/{draw_schedule_id}/{branch_id}/{date}")
def get_tickets_by_schedule(request: Request, draw_schedule_id: int, branch_id: int, date: date) -> dict:
    _require_auth(request)
    proc_name = settings.ticket_by_schedule
    if not proc_name:
        raise HTTPException(status_code=500, detail="Tickets by schedule stored procedure not configured")

    try:
        result_sets = call_stored_proc_multi(
            proc_name,
            {"schedule_id": draw_schedule_id, "branch_id": branch_id, "date": date},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Database error") from exc

    items = result_sets[0] if len(result_sets) > 0 else []
    details = result_sets[1] if len(result_sets) > 1 else []
    return {"items": items, "details": details}

@router.get("/by-winner/{winner_id}")
def get_tickets_by_winner(request: Request, winner_id: int) -> dict:
    _require_auth(request)
    proc_name = settings.ticket_by_winner
    if not proc_name:
        raise HTTPException(status_code=500, detail="Tickets by winner stored procedure not configured")

    try:
        result_sets = call_stored_proc_multi(
            proc_name,
            {"winner_id": winner_id},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Database error") from exc

    items = result_sets[0] if len(result_sets) > 0 else []
    details = result_sets[1] if len(result_sets) > 1 else []
    return {"items": items, "details": details}