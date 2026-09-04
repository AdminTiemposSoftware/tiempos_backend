from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from fastapi import APIRouter, Body, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from db import call_stored_proc, call_stored_proc_table_vars
from routers.auth import _require_auth

router = APIRouter(prefix="/number", tags=["number"])
routerOperations = APIRouter(prefix="/number/operations", tags=["operations"])

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
    _require_auth(request)
    proc_name = _get_proc(settings.number_by_draw_schedule, "Number by draw schedule stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("draw_schedule_id", draw_schedule_id)
    params.setdefault("branch_id", branch_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@router.post("/prohibited")
def create_prohibited(request: Request, payload: dict[str, object]) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.prohibited_create, "Prohibited create stored procedure not configured")
    payload = _get_payload(request, payload)
    rows = _call_proc(proc_name, payload)
    return {"items": rows}

@router.put("/prohibited/{id}")
def update_prohibited(request: Request, id: str, payload: dict[str, object]) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.prohibited_update, "Prohibited update stored procedure not configured")
    payload = _get_payload(request, payload)
    payload["id"] = id
    _call_proc(proc_name, payload)
    return {"items": []}

@router.get("/prohibited/by-banking/{banking_id}")
def get_prohibited_by_banking_id(banking_id: str, request: Request) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.prohibited_by_banking_id, "Prohibited by banking ID stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("banking_id", banking_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@router.get("/prohibited/by-branch/{branch_id}")
def get_prohibited_by_branch_id(branch_id: str, request: Request) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.prohibited_by_branch_id, "Prohibited by branch ID stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("branch_id", branch_id)
    rows = _call_proc(proc_name, params)
    return {"items": rows}

@router.delete("/prohibited/{banking_id}/{number_id}")
def delete_prohibited(request: Request, banking_id: str, number_id: str) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.prohibited_delete, "Prohibited delete stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("banking_id", banking_id)
    params.setdefault("number_id", number_id)
    _call_proc(proc_name, params)
    return {"items": []}

@router.get("/prohibited/filtered")
def get_prohibited_filtered(date_from: str, date_to: str, branches: str, request: Request) -> dict:
    _require_auth(request)
    proc_name = _get_proc(settings.prohibited_filtered, "Prohibited filtered stored procedure not configured")
    params = {
        "date_from": date_from,
        "date_to": date_to
    }
    branches_list = [(int(x),) for x in branches.split(",")]
    table_params = [
        {
            "param": "branches",
            "type": "dbo.id_list",
            "columns": ["id"],
            "rows": branches_list
        }
    ]
    rows = call_stored_proc_table_vars(proc_name, params, table_params)
    return {"items": rows}


@routerOperations.get("/")
def get_operations():
    return {"items": []}

def _to_decimal_str(value: object, field_name: str) -> str:
    try:
        normalized = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return format(normalized, "f")
    except (InvalidOperation, TypeError):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a decimal value") from None


@routerOperations.post("")
def create_operation(
    request: Request,
    payload: dict[str, object] | None = Body(default=None),
) -> dict:
    _require_auth(request)
    proc_name = _get_proc(
        settings.number_total_operation_create,
        "Number total operation create stored procedure not configured",
    )
    params = _get_payload(request, payload)

    operations = params.get("operations")
    if not isinstance(operations, list) or not operations:
        raise HTTPException(status_code=400, detail="operations must be a non-empty list")

    date = params.get("date")
    if date is None or str(date).strip() == "":
        raise HTTPException(status_code=400, detail="date is required")

    table_rows: list[tuple[str, int, str]] = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise HTTPException(status_code=400, detail="Each operation must be an object")

        operation_code = operation.get("operation")
        number_total_id = operation.get("number_total_id")
        amount = operation.get("amount")

        if operation_code is None or str(operation_code).strip() == "":
            raise HTTPException(status_code=400, detail="Each operation must include operation")
        try:
            parsed_number_total_id = int(number_total_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Each operation must include a valid number_total_id") from None
        if parsed_number_total_id <= 0:
            raise HTTPException(status_code=400, detail="Each operation must include a valid number_total_id")
        if amount is None:
            raise HTTPException(status_code=400, detail="Each operation must include amount")

        table_rows.append((str(operation_code), parsed_number_total_id, _to_decimal_str(amount, "operations.amount")))

    rows = call_stored_proc_table_vars(
        proc_name,
        {"date": date},
        [{
            "param": "operations",
            "type": "dbo.number_total_operation_list",
            "columns": ["operation", "number_total_id", "amount"],
            "rows": table_rows,
        }],
    )
    return {"items": rows}
