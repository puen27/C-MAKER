"""요청 단위 DB 커넥션 의존성. 정상 종료 시 commit, 예외 시 rollback된다."""

from __future__ import annotations

from collections.abc import Iterator

import psycopg

from backend.common.db.pool import get_connection


def get_db() -> Iterator[psycopg.Connection]:
    with get_connection() as conn:
        yield conn
