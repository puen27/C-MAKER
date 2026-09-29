from __future__ import annotations

from typing import Any

import psycopg

_SELECT = """
    SELECT t.id, t.signal_type, t.category, t.label, t.description, t.threshold_value::float8 AS threshold_value,
           t.unit, t.is_fixed, t.integer_only, t.min_value::float8 AS min_value, t.max_value::float8 AS max_value,
           u.name AS updated_by_name, t.updated_at
    FROM threshold_config t
    LEFT JOIN app_user u ON u.id = t.updated_by
"""


def list_all(conn: psycopg.Connection) -> list[dict[str, Any]]:
    return conn.execute(f"{_SELECT} ORDER BY t.category, t.id").fetchall()


def get(conn: psycopg.Connection, threshold_id: int, *, for_update: bool = False) -> dict[str, Any] | None:
    lock = " FOR UPDATE OF t" if for_update else ""
    return conn.execute(f"{_SELECT} WHERE t.id = %s{lock}", (threshold_id,)).fetchone()


def get_by_signal_type(conn: psycopg.Connection, signal_type: str) -> dict[str, Any] | None:
    return conn.execute(f"{_SELECT} WHERE t.signal_type = %s", (signal_type,)).fetchone()


def update_value(conn: psycopg.Connection, threshold_id: int, value: float, user_id: int) -> None:
    conn.execute(
        "UPDATE threshold_config SET threshold_value = %s, updated_by = %s, updated_at = now() WHERE id = %s",
        (value, user_id, threshold_id),
    )
