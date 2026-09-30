"""BATCH_RUN CRUD (REQ-17, UC-18)."""

from __future__ import annotations

from datetime import date
from typing import Any

import psycopg

_SELECT = """
    SELECT r.id, r.run_type, r.status, r.target_date, r.requested_at, r.started_at, r.completed_at,
           r.failure_reason, r.triggered_by, r.source_status, u.name AS triggered_by_name
    FROM batch_run r
    LEFT JOIN app_user u ON u.id = r.triggered_by
"""


def get(conn: psycopg.Connection, run_id: int) -> dict[str, Any] | None:
    return conn.execute(f"{_SELECT} WHERE r.id = %s", (run_id,)).fetchone()


def latest(conn: psycopg.Connection) -> dict[str, Any] | None:
    return conn.execute(f"{_SELECT} ORDER BY r.requested_at DESC, r.id DESC LIMIT 1").fetchone()


def running(conn: psycopg.Connection) -> dict[str, Any] | None:
    return conn.execute(f"{_SELECT} WHERE r.status = 'RUNNING' LIMIT 1").fetchone()


def latest_finished_for_date(conn: psycopg.Connection, day: date) -> dict[str, Any] | None:
    return conn.execute(
        f"{_SELECT} WHERE r.target_date = %s AND r.status <> 'RUNNING' ORDER BY r.completed_at DESC NULLS LAST, r.id DESC LIMIT 1",
        (day,),
    ).fetchone()


def last_manual_request(conn: psycopg.Connection, user_id: int) -> dict[str, Any] | None:
    return conn.execute(
        """
        SELECT id, requested_at FROM batch_run
        WHERE triggered_by = %s AND run_type = 'MANUAL'
        ORDER BY requested_at DESC LIMIT 1
        """,
        (user_id,),
    ).fetchone()


def create_manual_run(conn: psycopg.Connection, user_id: int, target_date: date) -> int | None:
    """CONST-17 부분 유니크 인덱스로 동시 요청 경쟁까지 막는다. RUNNING이 이미 있으면 None."""
    row = conn.execute(
        """
        INSERT INTO batch_run (run_type, status, triggered_by, target_date)
        VALUES ('MANUAL', 'RUNNING', %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        (user_id, target_date),
    ).fetchone()
    return int(row["id"]) if row else None


def mark_failed(conn: psycopg.Connection, run_id: int, reason: str) -> bool:
    cursor = conn.execute(
        """
        UPDATE batch_run SET status = 'FAILED', completed_at = now(), failure_reason = %s
        WHERE id = %s AND status = 'RUNNING'
        """,
        (reason, run_id),
    )
    return cursor.rowcount > 0


def fail_stale(conn: psycopg.Connection, stale_minutes: int) -> int:
    cursor = conn.execute(
        """
        UPDATE batch_run SET status = 'FAILED', completed_at = now(),
               failure_reason = '비정상 종료로 판단되어 실패 처리됨(RUNNING 상태 장기 지속)'
        WHERE status = 'RUNNING' AND COALESCE(started_at, requested_at) < now() - make_interval(mins => %s)
        """,
        (stale_minutes,),
    )
    return cursor.rowcount


def average_duration_seconds(conn: psycopg.Connection, sample: int = 10) -> float | None:
    row = conn.execute(
        """
        SELECT avg(EXTRACT(EPOCH FROM (completed_at - started_at))) AS seconds
        FROM (
            SELECT started_at, completed_at FROM batch_run
            WHERE status = 'SUCCESS' AND started_at IS NOT NULL AND completed_at IS NOT NULL
            ORDER BY completed_at DESC LIMIT %s
        ) recent
        """,
        (sample,),
    ).fetchone()
    return float(row["seconds"]) if row and row["seconds"] is not None else None
