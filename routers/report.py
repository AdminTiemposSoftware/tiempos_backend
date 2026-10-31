from datetime import date, datetime, timedelta
from threading import Lock
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from db import call_stored_proc, call_stored_proc_table_vars
from routers.auth import _require_auth

router = APIRouter(prefix="/report", tags=["report"])

# This cache is process-local; deployments with multiple workers/instances do
# not share entries and may query once per worker. Use a shared cache only if
# cross-instance reuse becomes a deployment requirement.
_CACHE_TTL = timedelta(minutes=5)
_cache: dict[tuple, tuple[datetime, dict]] = {}
_cache_lock = Lock()
_inflight_locks: dict[tuple, Lock] = {}
_VALID_GROUPING_MODES = {"branch", "draw_schedule", "draw", "date"}

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


def _normalize_dates(rows: list[dict]) -> list[dict]:
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


def _group_value(item: dict, mode: str) -> str:
    return _date_key(item.get("date")) if mode == "date" else str(item.get({
        "branch": "branch_id",
        "draw_schedule": "draw_schedule_id",
        "draw": "draw_id",
    }[mode], ""))


def _group_label(item: dict, mode: str) -> str:
    return _date_key(item.get("date")) if mode == "date" else str(item.get({
        "branch": "branch_name",
        "draw_schedule": "draw_schedule_name",
        "draw": "draw_name",
    }[mode], ""))


def _scope_key(item: dict) -> str:
    return (
        f"{_date_key(item.get('date'))}|"
        f"{_number(item.get('branch_id')):g}|"
        f"{_number(item.get('draw_schedule_id')):g}"
    )


def _configured_percentage(item: dict, prohibited: dict) -> float:
    for source in (prohibited, item):
        for field in (
            "percentage",
            "prohibited_percentage",
            "branch_prohibited_percentage",
            "draw_schedule_branch_prohibited_percentage",
        ):
            value = source.get(field)
            if value is not None and str(value).strip() != "":
                return _number(value)
    return 0.0


def _calculate_groups(items: list[dict], winners: list[dict], prohibited: list[dict],
                      grouping_modes: list[str]) -> tuple[list[dict], dict[str, float]]:
    modes = grouping_modes or ["date", "draw_schedule"]
    unique_winners = {winner.get("winner_id"): winner for winner in winners
                      if winner.get("winner_id") is not None}
    winners_by_schedule: dict[str, list[dict]] = {}
    for winner in unique_winners.values():
        key = f"{_date_key(winner.get('date'))}|{winner.get('schedule_id', winner.get('draw_schedule_id'))}"
        winners_by_schedule.setdefault(key, []).append(winner)
    prohibited_by_number: dict[str, list[dict]] = {}
    for row in prohibited:
        key = f"{row.get('date')}|{_number(row.get('number')):g}"
        prohibited_by_number.setdefault(key, []).append(row)
    scope_totals: dict[str, float] = {}
    for item in items:
        key = _scope_key(item)
        scope_totals[key] = scope_totals.get(key, 0) + _number(item.get("amount"))

    primary: dict[str, dict] = {}
    secondary_modes = modes[1:] or modes
    for item in items:
        amount = _number(item.get("amount"))
        scope_key = _scope_key(item)
        candidates = prohibited_by_number.get(
            f"{item.get('date')}|{_number(item.get('number')):g}", []
        )
        prohibited_row = next((row for row in candidates
                if (row.get("branch_id") is None)
                or (_number(row.get("branch_id")) == _number(item.get("branch_id")))),
            None,
        )
        devolution = 0.0
        if prohibited_row:
            if _flag(prohibited_row.get("by_amount")):
                limit = _number(prohibited_row.get("amount"))
                devolution = max(amount - limit, 0)
            elif _flag(prohibited_row.get("by_percentage")):
                starter = _number(prohibited_row.get("starter"))
                percentage = _configured_percentage(item, prohibited_row)
                limit = scope_totals[scope_key] * percentage * .01
                devolution = max(amount - limit, 0) if amount > starter else 0
        winner_key = f"{_date_key(item.get('date'))}|{item.get('draw_schedule_id')}"
        row_winners = winners_by_schedule.get(winner_key, [])
        winner_total = 0.0
        for winner in row_winners:
            if float(winner.get("winner_number") or -1) == float(item.get("number") or -2):
                winner_total += (amount - devolution) * _number(winner.get("position_multiplier"))
                first_place = item.get("branch_buy_first_place")
                if first_place is not None:
                    winner_total += devolution * _number(first_place)
        p_id, s_id = _group_value(item, modes[0]), "|".join(_group_value(item, m) for m in secondary_modes)
        group = primary.setdefault(p_id, {"id": p_id, "label": _group_label(item, modes[0]), "rows": {}})
        row = group["rows"].setdefault(s_id, {
            "id": s_id,
            "label": " - ".join(_group_label(item, m) for m in secondary_modes),
            "winners": row_winners.copy(), "winner_total": 0.0, "overageNumbers": [],
            "total": 0.0, "devolution": 0.0, "comission": 0.0, "buy": 0.0,
        })
        row["total"] += amount
        row["devolution"] += devolution
        row["winner_total"] += winner_total
        # Rates belong to each source item. Add each item's contribution
        # instead of applying the last item's rate to the cumulative row.
        row["comission"] += (amount - devolution) * _number(item.get("branch_comission")) * .01
        row["buy"] += devolution * _number(item.get("branch_buy")) * .01
        row["net"] = row["total"] - row["comission"] - row["winner_total"]
        row["winner_numbers"] = [
            winner.get("winner_number") for winner in row["winners"]
            if winner.get("winner_number") is not None
        ]
        if prohibited_row:
            row["overageNumbers"].append({"number": item.get("number"), "amount": amount,
                                          "overage": 0, "prohibited": prohibited_row})
    result = []
    totals = {"total": 0.0, "comission": 0.0, "devolution": 0.0, "buy": 0.0, "winner_total": 0.0, "net": 0.0}
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
            totals["net"] += row["net"]
        group["net"] = group["total"] - group["comission"] - group["winner_total"]
        group["rows"] = rows
        if rows:
            result.append(group)
    return result, totals

@router.get("/today/{banking_id}")
def get_report_of_today(banking_id: str, request: Request) -> dict:
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
) -> tuple[dict, bool]:
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
) -> dict:
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
    return {
        "items": base["items"],
        "winnersFilteredItems": base["winners"],
        "prohibitedFilteredItems": base["prohibited"],
        "cache": {"hit": cache_hit, "ttl_seconds": int(_CACHE_TTL.total_seconds())},
    }


@router.get("/filtered")
def get_filtered_report(
    date_from: str,
    date_to: str, branches: str, draw_schedules: str, request: Request,
    grouping_modes: str = Query("date,draw_schedule"),
) -> dict:
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
