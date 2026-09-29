"""감사 추적 로그 (REQ-15). 태깅 이력은 학습 용도 외 집계에 쓰지 않는다(CLAUDE.md §0.7)."""

from __future__ import annotations

import json
from typing import Any

import psycopg


def _json(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False, default=str)


def insert(
    conn: psycopg.Connection,
    *,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    before_value: Any = None,
    after_value: Any = None,
) -> None:
    conn.execute(
        """
        INSERT INTO audit_log (actor_user_id, action, entity_type, entity_id, before_value, after_value)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)
        """,
        (actor_user_id, action, entity_type, entity_id, _json(before_value), _json(after_value)),
    )


def list_for_entity(conn: psycopg.Connection, entity_type: str, entity_id: str, limit: int = 100) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT a.id, a.action, a.before_value, a.after_value, a.created_at, u.name AS actor_name
        FROM audit_log a
        LEFT JOIN app_user u ON u.id = a.actor_user_id
        WHERE a.entity_type = %s AND a.entity_id = %s
        ORDER BY a.created_at DESC, a.id DESC
        LIMIT %s
        """,
        (entity_type, entity_id, limit),
    ).fetchall()
