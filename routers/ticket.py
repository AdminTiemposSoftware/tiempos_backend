import secrets
from datetime import date, datetime, timedelta, timezone
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

# TODO: Consider using a more robust method for generating unique serials, such as a database sequence or UUIDs, to avoid potential collisions in high-concurrency scenarios.
def _generate_serial() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _is_duplicate_serial_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "serial already exists" in message or "uq_ticket_header_serial" in message

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

    numbers = payload.get("numbers")
    if not isinstance(numbers, list) or not numbers:
        raise HTTPException(status_code=400, detail="numbers must be a non-empty list")

    number_rows = []
    for number in numbers:
        number_rows.append(
            (
                number["number"],
                _to_decimal_str(number.get("amount"), "numbers.amount"),
                number["is_reventado"],
                number["is_megareventado"],
            )
        )

    # Calculate total amount from numbers
    try:
        total_amount = sum(Decimal(str(number.get("amount", 0))) for number in numbers)
    except (InvalidOperation, TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Each numbers.amount must be a valid decimal value")

    printed_at = datetime.now() + timedelta(hours=settings.HOUR_OFFSET)

    last_error: Exception | None = None
    # TODO : Implement a more robust mechanism for generating unique serials, possibly using a database sequence or UUIDs.
    for _ in range(10):
        params = {
            "draw_schedule_id": payload.get("draw_schedule_id"),
            "branch_id": payload.get("branch_id"),
            "details": payload.get("details"),
            "serial": _generate_serial(),
            "amount": _to_decimal_str(total_amount, "amount"),
            "printed_at": printed_at.isoformat(),
        }

        try:
            rows = call_stored_proc_table_var(
                proc_name,
                params=params,
                table_param="numbers",
                table_type="dbo.ticket_detail_list",
                table_columns=["number", "amount", "is_reventado", "is_megareventado"],
                table_rows=number_rows,
            )
            return {"items": rows}
        except SQLAlchemyError as exc:
            if _is_duplicate_serial_error(exc):
                last_error = exc
                continue
            raise HTTPException(status_code=500, detail="Database error") from exc

    raise HTTPException(status_code=500, detail="Unable to generate a unique ticket serial") from last_error

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
    numbers = result_sets[1] if len(result_sets) > 1 else []
    return {"items": items, "numbers": numbers}

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
    numbers = result_sets[1] if len(result_sets) > 1 else []
    return {"items": items, "numbers": numbers}