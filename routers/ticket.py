from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from db import call_stored_proc, call_stored_proc_table_var

router = APIRouter(prefix="/ticket", tags=["ticket"])


def _to_decimal_str(value: object, field_name: str) -> str:
    try:
        normalized = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return format(normalized, "f")
    except (InvalidOperation, TypeError):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a decimal value")


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

    params = {
        "draw_schedule_id": payload.get("draw_schedule_id"),
        "branch_id": payload.get("branch_id"),
        "serial": payload.get("serial"),
        "amount": _to_decimal_str(payload.get("amount"), "amount"),
        "printed_at": payload.get("printed_at"),
        "enabled": payload.get("enabled", 1),
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