from typing import Mapping, Optional

import re

from sqlalchemy import create_engine, text

from config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.pool_size,
    max_overflow=settings.max_overflow,
    pool_timeout=settings.pool_timeout,
    future=True,
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_QUALIFIED_IDENTIFIER_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$"
)


def _validate_identifier(value: str, label: str, allow_qualified: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} is required")
    pattern = _QUALIFIED_IDENTIFIER_RE if allow_qualified else _IDENTIFIER_RE
    if not pattern.match(value):
        raise ValueError(f"Invalid {label}")
    return value

def call_stored_proc(proc_name: str, params: Optional[Mapping[str, object]] = None) -> list[dict]:
    conn = engine.raw_connection()
    cursor = None
    try:
        # print(f"Calling stored procedure: {proc_name} with params: {params}")
        _validate_identifier(proc_name, "proc_name", allow_qualified=True)
        cursor = conn.cursor()
        if params:
            items = list(params.items())
            for key, _ in items:
                _validate_identifier(key, "param name")
            assignments = ", ".join(f"@{key}=?" for key, _ in items)
            sql = f"EXEC {proc_name} {assignments}"
            values = [value for _, value in items]
            cursor.execute(sql, values)
        else:
            sql = f"EXEC {proc_name}"
            cursor.execute(sql)

        rows = cursor.fetchall() if cursor.description else []
        columns = [col[0] for col in cursor.description] if cursor.description else []
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()

    return [dict(zip(columns, row)) for row in rows]


def call_stored_proc_multi(
    proc_name: str, params: Optional[Mapping[str, object]] = None
) -> list[list[dict]]:
    conn = engine.raw_connection()
    cursor = None
    try:
        _validate_identifier(proc_name, "proc_name", allow_qualified=True)
        cursor = conn.cursor()
        if params:
            items = list(params.items())
            for key, _ in items:
                _validate_identifier(key, "param name")
            assignments = ", ".join(f"@{key}=?" for key, _ in items)
            sql = f"EXEC {proc_name} {assignments}"
            values = [value for _, value in items]
            cursor.execute(sql, values)
        else:
            sql = f"EXEC {proc_name}"
            cursor.execute(sql)

        result_sets: list[list[dict]] = []
        while True:
            if cursor.description:
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                result_sets.append([dict(zip(columns, row)) for row in rows])
            else:
                result_sets.append([])

            if not cursor.nextset():
                break

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()

    return result_sets


def call_stored_proc_table_var(
    proc_name: str,
    params: Mapping[str, object],
    table_param: str,
    table_type: str,
    table_columns: list[str],
    table_rows: list[tuple[object, ...]],
) -> list[dict]:
    conn = engine.raw_connection()
    cursor = None
    try:
        cursor = conn.cursor()
        _validate_identifier(proc_name, "proc_name", allow_qualified=True)
        _validate_identifier(table_param, "table_param")
        _validate_identifier(table_type, "table_type", allow_qualified=True)
        if not table_columns:
            raise ValueError("Table columns are required")
        if not table_rows:
            raise ValueError("Table rows are required")
        for column in table_columns:
            _validate_identifier(column, "table column")

        row_placeholders = ", ".join(
            "(" + ", ".join(["?"] * len(table_columns)) + ")" for _ in table_rows
        )
        insert_sql = (
            f"INSERT INTO @{table_param} ("
            f"{', '.join(table_columns)}) VALUES {row_placeholders};"
        )

        scalar_items = list(params.items())
        for key, _ in scalar_items:
            _validate_identifier(key, "param name")
        exec_assignments = ", ".join(
            [f"@{key}=?" for key, _ in scalar_items] + [f"@{table_param}=@{table_param}"]
        )
        sql = f"DECLARE @{table_param} {table_type}; {insert_sql} EXEC {proc_name} {exec_assignments}"
        values = [value for row in table_rows for value in row] + [value for _, value in scalar_items]

        cursor.execute(sql, values)

        while cursor.description is None and cursor.nextset():
            pass

        rows = cursor.fetchall() if cursor.description else []
        columns = [col[0] for col in cursor.description] if cursor.description else []
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()

    return [dict(zip(columns, row)) for row in rows]



def ping() -> bool:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True