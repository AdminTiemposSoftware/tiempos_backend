from datetime import date, datetime, timedelta
from threading import Lock
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from db import call_stored_proc, call_stored_proc_table_vars
from routers.auth import _require_auth

router = APIRouter(prefix="/report", tags=["report"])

Row = dict[str, Any]
Rows = list[Row]

# This cache is process-local; deployments with multiple workers/instances do
# not share entries and may query once per worker. Use a shared cache only if
# cross-instance reuse becomes a deployment requirement.
_CACHE_TTL = timedelta(minutes=5)
_cache: dict[tuple[Any, ...], tuple[datetime, Row]] = {}
_cache_lock = Lock()
_inflight_locks: dict[tuple[Any, ...], Lock] = {}
_VALID_GROUPING_MODES = {"branch", "draw_schedule", "draw", "date"}

def _get_proc(proc_name: str | None, detail: str) -> str:
    if not proc_name:
        raise HTTPException(status_code=500, detail=detail)
    return proc_name

def _call_proc(proc_name: str, params: dict[str, object] | None = None) -> Rows:
    try:
        return call_stored_proc(proc_name, params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail="Database error") from exc


def _parse_ids(value: str, name: str) -> list[int]:
    try:
        ids = sorted({int(part.strip()) for part in value.split(",") if part.strip()})
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{name} must contain integer IDs") from None
    if not ids or any(value <= 0 for value in ids):
        raise HTTPException(status_code=400, detail=f"{name} must contain at least one positive ID")
    return ids


def _date_key(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "").replace("T", " ", 1).split(" ", 1)[0]


def _normalize_dates(rows: Rows) -> Rows:
    return [
        {**row, "date": _date_key(row["date"])}
        if row.get("date") is not None else row
        for row in rows
    ]


def _number(value: object, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if parsed == parsed else default
    except (TypeError, ValueError):
        return default


def _flag(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _group_value(item: Row, mode: str) -> str:
    return _date_key(item.get("date")) if mode == "date" else str(item.get({
        "branch": "branch_id",
        "draw_schedule": "draw_schedule_id",
        "draw": "draw_id",
    }[mode], ""))


def _group_label(item: Row, mode: str) -> str:
    return _date_key(item.get("date")) if mode == "date" else str(item.get({
        "branch": "branch_name",
        "draw_schedule": "draw_schedule_name",
        "draw": "draw_name",
    }[mode], ""))


def _scope_key(item: Row) -> str:
    return (
        f"{_date_key(item.get('date'))}|"
        f"{_number(item.get('branch_id')):g}|"
        f"{_number(item.get('draw_schedule_id')):g}"
    )


def _configured_percentage(item: Row, prohibited: Row) -> float:
    for source in (prohibited, item):
        for field in (
            "draw_schedule_branch_prohibited_percentage",
            "branch_prohibited_percentage",
        ):
            value = source.get(field)
            if value is not None and str(value).strip() != "":
                return _number(value)
    return 0.0


def _index_winners(winners: Rows) -> dict[str, Rows]:
    unique = {
        winner.get("winner_id"): winner
        for winner in winners
        if winner.get("winner_id") is not None
    }
    indexed: dict[str, Rows] = {}
    for winner in unique.values():
        key = f"{_date_key(winner.get('date'))}|{winner.get('schedule_id', winner.get('draw_schedule_id'))}"
        indexed.setdefault(key, []).append(winner)
    return indexed


def _index_prohibited(prohibited: Rows) -> dict[str, Rows]:
    indexed: dict[str, Rows] = {}
    for row in prohibited:
        key = f"{_date_key(row.get('date'))}|{_number(row.get('number')):g}"
        indexed.setdefault(key, []).append(row)
    return indexed


def _find_prohibited(item: Row, prohibited_by_number: dict[str, Rows]) -> Row | None:
    candidates = prohibited_by_number.get(
        f"{_date_key(item.get('date'))}|{_number(item.get('number')):g}", []
    )
    return next(
        (
            row for row in candidates
            if row.get("branch_id") is None
            or _number(row.get("branch_id")) == _number(item.get("branch_id"))
        ),
        None,
    )


def _calculate_devolution(
    item: Row, prohibited: Row | None, scope_total: float,
) -> tuple[float, float | None, float, str | None]:
    if prohibited is None:
        return 0.0, None, 0.0, None
    if _flag(prohibited.get("by_amount")):
        limit = _number(prohibited.get("amount"))
        return max(_number(item.get("amount")) - limit, 0), None, limit, "amount"
    if _flag(prohibited.get("by_percentage")):
        percentage = _configured_percentage(item, prohibited)
        limit = scope_total * percentage * .01
        devolution = (
            max(_number(item.get("amount")) - limit, 0)
            if _number(item.get("amount")) > _number(prohibited.get("starter"))
            else 0
        )
        return devolution, percentage, limit, "percentage"
    return 0.0, None, 0.0, None


def _prepare_items(
    items: Rows, winners: Rows, prohibited: Rows,
) -> Rows:
    winners_by_schedule = _index_winners(winners)
    prohibited_by_number = _index_prohibited(prohibited)
    scope_totals: dict[str, float] = {}
    for item in items:
        key = _scope_key(item)
        scope_totals[key] = scope_totals.get(key, 0.0) + _number(item.get("amount"))

    prepared = []
    for item in items:
        amount = _number(item.get("amount"))
        prohibited_row = _find_prohibited(item, prohibited_by_number)
        devolution, percentage, limit, devolution_mode = _calculate_devolution(
            item, prohibited_row, scope_totals[_scope_key(item)]
        )
        winner_key = f"{_date_key(item.get('date'))}|{item.get('draw_schedule_id')}"
        row_winners = winners_by_schedule.get(winner_key, [])
        winner_base = sum(
            (amount - devolution) * _number(winner.get("position_multiplier"))
            for winner in row_winners
            if float(winner.get("winner_number") or -1) == float(item.get("number") or -2)
        )
        devolution_winner_total = sum(
            devolution * _number(item.get("branch_buy_first_place"))
            for winner in row_winners
            if float(winner.get("winner_number") or -1) == float(item.get("number") or -2)
            and item.get("branch_buy_first_place") is not None
        )
        prepared.append({
            "item": item,
            "amount": amount,
            "prohibited": prohibited_row,
            "devolution": devolution,
            "devolution_percentage": percentage,
            "devolution_limit": limit,
            "devolution_mode": devolution_mode,
            "winners": row_winners,
            "winner_base": winner_base,
            "devolution_winner_total": devolution_winner_total,
            "winner_total": winner_base + devolution_winner_total,
            "comission": (amount - devolution) * _number(item.get("branch_comission")) * .01,
            "buy": devolution * _number(item.get("branch_buy")) * .01,
        })
    return prepared


def _calculate_groups(items: Rows, winners: Rows, prohibited: Rows,
                      grouping_modes: list[str], prepared: Rows | None = None,
                      ) -> tuple[Rows, dict[str, float]]:
    modes = grouping_modes or ["date", "draw_schedule"]
    prepared = prepared if prepared is not None else _prepare_items(items, winners, prohibited)

    primary: dict[str, Row] = {}
    secondary_modes = modes[1:] or modes
    for calculated in prepared:
        item = calculated["item"]
        amount = calculated["amount"]
        prohibited_row = calculated["prohibited"]
        devolution = calculated["devolution"]
        row_winners = calculated["winners"]
        winner_total = calculated["winner_total"]
        winner_base = calculated["winner_base"]
        devolution_winner_total = calculated["devolution_winner_total"]
        p_id, s_id = _group_value(item, modes[0]), "|".join(_group_value(item, m) for m in secondary_modes)
        group = primary.setdefault(p_id, {"id": p_id, "label": _group_label(item, modes[0]), "rows": {}})
        row = group["rows"].setdefault(s_id, {
            "id": s_id,
            "label": " - ".join(_group_label(item, m) for m in secondary_modes),
            "winners": row_winners.copy(), "winner_total": 0.0, "overageNumbers": [],
            "total": 0.0, "devolution": 0.0, "comission": 0.0, "buy": 0.0,
            "winner_base": 0.0, "devolution_winner_total": 0.0,
        })
        row["total"] += amount
        row["devolution"] += devolution
        row["winner_total"] += winner_total
        row["winner_base"] += winner_base
        row["devolution_winner_total"] += devolution_winner_total
        # Rates belong to each source item. Add each item's contribution
        # instead of applying the last item's rate to the cumulative row.
        row["comission"] += calculated["comission"]
        row["buy"] += calculated["buy"]
        row["net"] = row["total"] - row["comission"] - row["winner_total"]
        row["winner_numbers"] = [
            winner.get("winner_number") for winner in row["winners"]
            if winner.get("winner_number") is not None
        ]
        if prohibited_row:
            row["overageNumbers"].append({"number": item.get("number"), "amount": amount,
                                          "overage": 0, "prohibited": prohibited_row})
    result = []
    totals = {
        "total": 0.0, "comission": 0.0, "devolution": 0.0, "buy": 0.0,
        "winner_total": 0.0, "winner_base": 0.0,
        "devolution_winner_total": 0.0, "net": 0.0,
    }
    for group in sorted(primary.values(), key=lambda value: value["label"]):
        group.update({
            "total": 0.0,
            "comission": 0.0,
            "devolution": 0.0,
            "buy": 0.0,
            "winner_total": 0.0,
            "net": 0.0,
        })
        rows = sorted((row for row in group["rows"].values() if row["total"] != 0),
                      key=lambda value: value["total"], reverse=True)
        for row in rows:
            for key in ("total", "comission", "devolution", "buy", "winner_total"):
                group[key] += row[key]
                totals[key] += row[key]
            totals["winner_base"] += row["winner_base"]
            totals["devolution_winner_total"] += row["devolution_winner_total"]
            totals["net"] += row["net"]
        group["net"] = group["total"] - group["comission"] - group["winner_total"]
        group["rows"] = rows
        if rows:
            result.append(group)
    return result, totals


def _calculate_number_report(
    items: Rows, winners: Rows, prohibited: Rows,
) -> tuple[Rows, dict[str, Rows], Rows, dict[str, float]]:
    """Return the compact matrix payload and the calculations used by its summary."""
    prepared = _prepare_items(items, winners, prohibited)
    _, totals = _calculate_groups(
        items, winners, prohibited, ["draw", "draw_schedule", "branch"], prepared
    )
    numbers = {number: 0.0 for number in range(100)}
    breakdown: dict[str, dict[tuple[Any, ...], Row]] = {}
    devolution_rows: dict[tuple[Any, ...], Row] = {}
    for calculated in prepared:
        item = calculated["item"]
        number = int(_number(item.get("number"), -1))
        if not 0 <= number <= 99:
            continue
        amount = calculated["amount"]
        numbers[number] += amount
        key = (
            str(item.get("draw_name") or ""),
            str(item.get("draw_schedule_name") or ""),
            str(item.get("branch_name") or ""),
        )
        row = breakdown.setdefault(str(number), {}).setdefault(key, {
            "draw": key[0], "draw_schedule": key[1], "branch": key[2], "total": 0.0,
        })
        row["total"] += amount

        mode = calculated["devolution_mode"]
        if mode is None:
            continue
        percentage = calculated["devolution_percentage"]
        limit = calculated["devolution_limit"]
        devolution = calculated["devolution"]
        if devolution <= 0:
            continue
        detail_key = (
            number, _date_key(item.get("date")), str(item.get("branch_name") or ""),
            str(item.get("draw_schedule_name") or ""),
        )
        detail = devolution_rows.setdefault(detail_key, {
            "number": number,
            "date": item.get("date"),
            "branch": str(item.get("branch_name") or ""),
            "schedule": str(item.get("draw_schedule_name") or ""),
            "amount": 0.0,
            "limit": limit,
            "percentage": percentage,
            "percentageLimit": limit if mode == "percentage" else 0.0,
            "devolution": 0.0,
            "mode": mode,
        })
        detail["amount"] += amount
        detail["devolution"] += devolution

    devolution_by_number: dict[int, Row] = {}
    for detail in devolution_rows.values():
        number = detail["number"]
        row = devolution_by_number.setdefault(number, {
            "number": number,
            "date": detail["date"],
            "branch": detail["branch"],
            "schedule": detail["schedule"],
            "amount": 0.0,
            "limit": 0.0,
            "percentageLimit": 0.0,
            "percentage": detail["percentage"],
            "devolution": 0.0,
            "mode": detail["mode"],
            "details": [],
        })
        if row["mode"] != detail["mode"] or row["percentage"] != detail["percentage"]:
            row["mode"] = "mixed"
            row["percentage"] = None
        row["amount"] += detail["amount"]
        row["limit"] += detail["limit"]
        row["percentageLimit"] += detail["percentageLimit"]
        row["devolution"] += detail["devolution"]
        row["details"].append({
            key: detail[key] for key in (
                "date", "branch", "schedule", "amount", "limit",
                "percentage", "devolution", "mode",
            )
        })

    return (
        [{"number": number, "total": total} for number, total in numbers.items()],
        {number: list(rows.values()) for number, rows in breakdown.items()},
        list(devolution_by_number.values()),
        totals,
    )


def _summary_values(totals: dict[str, float]) -> dict[str, float]:
    total = totals["total"]
    devolution = totals["devolution"]
    commission = totals["comission"]
    winner_total = totals.get("winner_base", totals["winner_total"])
    devolution_winner_total = totals.get("devolution_winner_total", 0.0)
    adjusted_total = total - devolution
    net_devolution = devolution - devolution_winner_total
    net_total = adjusted_total - commission - winner_total
    return {
        "total": total,
        "devolution": devolution,
        "devolution_buy": totals["buy"],
        "devolution_winner_total": devolution_winner_total,
        "net_devolution": net_devolution,
        "adjusted_total": adjusted_total,
        "commission": commission,
        "winner_total": winner_total,
        "net_total": net_total,
        "real_commission": commission + totals["buy"],
        "real_winner_total": winner_total + devolution_winner_total,
        "real_net_total": net_total + net_devolution,
    }

@router.get("/today/{banking_id}")
def get_report_of_today(banking_id: str, request: Request) -> Row:
    _require_auth(request)
    proc_name = _get_proc(settings.report_today, "Report of today stored procedure not configured")
    params = {"banking_id": banking_id}
    rows = _call_proc(proc_name, params)
    return {"items": rows}


def _get_cached_base_report(
    date_from: str,
    date_to: str,
    branch_ids: list[int],
    schedule_ids: list[int],
    use_cache: bool = True,
) -> tuple[Row, bool]:
    cache_key = (date_from, date_to, tuple(branch_ids), tuple(schedule_ids))
    now = datetime.utcnow()
    with _cache_lock:
        request_lock = _inflight_locks.setdefault(cache_key, Lock())
    with request_lock:
        with _cache_lock:
            cached = _cache.get(cache_key)
            if use_cache and cached and now - cached[0] < _CACHE_TTL:
                return cached[1], True
            _cache.pop(cache_key, None)

        report_proc = _get_proc(settings.report_filtered, "Filtered report stored procedure not configured")
        winner_proc = _get_proc(settings.winner_filtered, "Filtered winner stored procedure not configured")
        prohibited_proc = _get_proc(settings.prohibited_filtered, "Filtered prohibited stored procedure not configured")
        params = {"date_from": date_from, "date_to": date_to}
        table = lambda name, rows: {
            "param": name, "type": "dbo.id_list", "columns": ["id"],
            "rows": [(value,) for value in rows],
        }
        try:
            base = {
                "items": call_stored_proc_table_vars(
                    report_proc, params,
                    [table("branches", branch_ids), table("draw_schedules", schedule_ids)],
                ),
                "winners": call_stored_proc_table_vars(
                    winner_proc, params,
                    [table("branches", branch_ids), table("draw_schedules", schedule_ids)],
                ),
                "prohibited": call_stored_proc_table_vars(
                    prohibited_proc, params, [table("branches", branch_ids)],
                ),
            }
            for key in ("items", "winners", "prohibited"):
                base[key] = _normalize_dates(base[key])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=500, detail="Database error") from exc
        with _cache_lock:
            _cache[cache_key] = (datetime.utcnow(), base)
        return base, False


@router.get("/base")
def get_base_report(
    date_from: str, date_to: str, branches: str, draw_schedules: str, request: Request,
) -> Row:
    _require_auth(request)
    try:
        parsed_from = date.fromisoformat(date_from)
        parsed_to = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(status_code=400, detail="date_from and date_to must be YYYY-MM-DD") from None
    if parsed_from > parsed_to:
        raise HTTPException(status_code=400, detail="date_from cannot be after date_to")
    branch_ids = _parse_ids(branches, "branches")
    schedule_ids = _parse_ids(draw_schedules, "draw_schedules")
    base, cache_hit = _get_cached_base_report(
        date_from, date_to, branch_ids, schedule_ids, use_cache=False
    )
    numbers, breakdown, devolution_breakdown, totals = _calculate_number_report(
        base["items"], base["winners"], base["prohibited"]
    )
    return {
        "numbers": numbers,
        "breakdown": breakdown,
        "devolutionBreakdown": devolution_breakdown,
        "summary": _summary_values(totals),
        "winnersFilteredItems": base["winners"],
        "prohibitedFilteredItems": base["prohibited"],
        "cache": {"hit": cache_hit, "ttl_seconds": int(_CACHE_TTL.total_seconds())},
    }


@router.get("/filtered")
def get_filtered_report(
    date_from: str,
    date_to: str, branches: str, draw_schedules: str, request: Request,
    grouping_modes: str = Query("date,draw_schedule"),
) -> Row:
    _require_auth(request)
    try:
        parsed_from = date.fromisoformat(date_from)
        parsed_to = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(status_code=400, detail="date_from and date_to must be YYYY-MM-DD") from None
    if parsed_from > parsed_to:
        raise HTTPException(status_code=400, detail="date_from cannot be after date_to")
    branch_ids = _parse_ids(branches, "branches")
    schedule_ids = _parse_ids(draw_schedules, "draw_schedules")
    modes = [mode.strip() for mode in grouping_modes.split(",") if mode.strip()]
    if not modes or any(mode not in _VALID_GROUPING_MODES for mode in modes) or len(set(modes)) != len(modes):
        raise HTTPException(status_code=400, detail="grouping_modes contains an invalid or duplicate mode")
    base, cache_hit = _get_cached_base_report(date_from, date_to, branch_ids, schedule_ids)
    groups, totals = _calculate_groups(base["items"], base["winners"], base["prohibited"], modes)
    return {
        "groups": groups,
        "totals": totals,
        "cache": {"hit": cache_hit, "ttl_seconds": int(_CACHE_TTL.total_seconds())},
    }
