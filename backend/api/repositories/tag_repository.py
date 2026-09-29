from __future__ import annotations

from typing import Any

import psycopg


def get_tag(conn: psycopg.Connection, recommendation_id: int) -> dict[str, Any] | None:
    return conn.execute(
        "SELECT tag_value, reject_reason, tagged_by, tagged_at FROM tag_feedback WHERE recommendation_id = %s",
        (recommendation_id,),
    ).fetchone()


def upsert_tag(
    conn: psycopg.Connection, recommendation_id: int, user_id: int, tag_value: str, reject_reason: str | None
) -> None:
    """추천 1건당 태깅은 최대 1건 — 재태깅은 갱신한다(ERD 3장)."""
    conn.execute(
        """
        INSERT INTO tag_feedback (recommendation_id, tagged_by, tag_value, reject_reason)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (recommendation_id) DO UPDATE SET
            tagged_by = EXCLUDED.tagged_by, tag_value = EXCLUDED.tag_value,
            reject_reason = EXCLUDED.reject_reason, tagged_at = now()
        """,
        (recommendation_id, user_id, tag_value, reject_reason),
    )


def delete_tag(conn: psycopg.Connection, recommendation_id: int) -> bool:
    cursor = conn.execute("DELETE FROM tag_feedback WHERE recommendation_id = %s", (recommendation_id,))
    return cursor.rowcount > 0
