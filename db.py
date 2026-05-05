from typing import Mapping, Optional

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

def call_stored_proc(proc_name: str, params: Optional[Mapping[str, object]] = None) -> list[dict]:
    conn = engine.raw_connection()
    cursor = None
    try:
        # print(f"Calling stored procedure: {proc_name} with params: {params}")
        cursor = conn.cursor()
        if params:
            items = list(params.items())
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


def ping() -> bool:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
