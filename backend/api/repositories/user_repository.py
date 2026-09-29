from __future__ import annotations

from typing import Any

import psycopg

_SELECT_USER = """
    SELECT u.id, u.username, u.name, u.role, u.password, u.branch_id, u.session_timeout_minutes,
           u.session_extendable, u.is_active, b.name AS branch_name, b.branch_code
    FROM app_user u
    LEFT JOIN branch b ON b.id = u.branch_id
"""


def find_by_username(conn: psycopg.Connection, username: str) -> dict[str, Any] | None:
    return conn.execute(f"{_SELECT_USER} WHERE u.username = %s", (username,)).fetchone()


def find_by_id(conn: psycopg.Connection, user_id: int) -> dict[str, Any] | None:
    return conn.execute(f"{_SELECT_USER} WHERE u.id = %s", (user_id,)).fetchone()
