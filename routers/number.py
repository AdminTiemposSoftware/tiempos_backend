from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from config import settings
from fastapi import APIRouter, Body, HTTPException, Request
from routers.auth import _require_auth
from sqlalchemy.exc import SQLAlchemyError

from db import call_stored_proc, call_stored_proc_table_vars, call_stored_proc_table_var

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


@routerOperations.get("/{draw_schedule_id}/{branch_id}/{date}/{is_reventado}/{is_megareventado}")
def get_total_operation(request: Request, draw_schedule_id: str, branch_id: str, date: str, is_reventado: str, is_megareventado: str):
    _require_auth(request)
    proc_name = _get_proc(settings.number_total_operation, "Number total operation stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("draw_schedule_id", draw_schedule_id)
    params.setdefault("branch_id", branch_id)
    params.setdefault("date", date)
    params.setdefault("is_reventado", is_reventado)
    params.setdefault("is_megareventado", is_megareventado)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.get("/registry/{draw_schedule_id}/{branch_id}/{date}/{is_reventado}/{is_megareventado}")
def get_registry(request: Request, draw_schedule_id: str, branch_id: str, date: str, is_reventado: str, is_megareventado: str):
    _require_auth(request)
    proc_name = _get_proc(settings.number_total_registry, "Number total registry stored procedure not configured")
    params = dict(request.query_params)
    params.setdefault("draw_schedule_id", draw_schedule_id)
    params.setdefault("branch_id", branch_id)
    params.setdefault("date", date)
    params.setdefault("is_reventado", is_reventado)
    params.setdefault("is_megareventado", is_megareventado)
    rows = _call_proc(proc_name, params)
    return {"items": rows}


@router.post("/registry")
def post_registry(
    request: Request,
    payload: dict[str, object] = Body(...),
) -> dict:
    _require_auth(request)
    proc_name = _get_proc(
        settings.number_total_registry_create,
        "Number total registry create stored procedure not configured",
    )

    draw_schedule_id = payload.get("draw_schedule_id")
    branch_id = payload.get("branch_id")
    registry_date = payload.get("date")
    is_reventado = payload.get("is_reventado")
    is_megareventado = payload.get("is_megareventado")
    numbers = payload.get("numbers")

    try:
        draw_schedule_id = int(draw_schedule_id)
        branch_id = int(branch_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="draw_schedule_id and branch_id must be valid integers",
        ) from None

    if draw_schedule_id <= 0 or branch_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="draw_schedule_id and branch_id must be positive integers",
        )

    if not isinstance(registry_date, str):
        raise HTTPException(status_code=400, detail="date is required")
    try:
        date.fromisoformat(registry_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be in YYYY-MM-DD format") from None

    if not isinstance(is_reventado, bool) or not isinstance(is_megareventado, bool):
        raise HTTPException(
            status_code=400,
            detail="is_reventado and is_megareventado must be boolean values",
        )

    if not isinstance(numbers, list) or len(numbers) != 100:
        raise HTTPException(status_code=400, detail="numbers must contain exactly 100 items")

    number_rows: list[tuple[int, str]] = []
    for index, number_item in enumerate(numbers):
        if not isinstance(number_item, dict):
            raise HTTPException(status_code=400, detail=f"numbers[{index}] must be an object")

        number = number_item.get("number")
        amount = number_item.get("amount")
        try:
            parsed_number = int(number)
            if parsed_number < 0 or parsed_number > 99:
                raise ValueError("number must be between 0 and 99")
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"numbers[{index}].number must be a valid integer",
            ) from None
        if amount is None:
            raise HTTPException(status_code=400, detail=f"numbers[{index}].amount is required")

        number_rows.append(
            (parsed_number, _to_decimal_str(amount, f"numbers[{index}].amount"))
        )

    try:
        rows = call_stored_proc_table_var(
            proc_name,
            params={
                "draw_schedule_id": draw_schedule_id,
                "date": registry_date,
                "branch_id": branch_id,
                "is_reventado": is_reventado,
                "is_megareventado": is_megareventado,
            },
            table_param="numbers",
            table_type="dbo.number_list",
            table_columns=["Number", "Amount"],
            table_rows=number_rows,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Database error") from exc

    return {"items": rows}
