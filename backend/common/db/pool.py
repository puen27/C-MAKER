"""psycopg 커넥션 풀 (OPS-02: 배치·API 프로세스 각각 시작 시 1회 생성해 재사용).

API 서버도 동기 풀(`ConnectionPool`)을 쓴다. FastAPI의 동기(def) 엔드포인트는 스레드풀에서 실행되므로
이 규모(지점 수백 단위)에서 충분하고, psycopg 비동기 모드가 Windows ProactorEventLoop를 지원하지 않는
문제(로컬 개발 환경)를 피할 수 있다. — docs/10-implementation-guide.md §5.1의 AsyncConnectionPool 대비 변경점.

모든 커넥션은 `search_path=<DB_SCHEMA>`, `timezone=Asia/Seoul`로 연다.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from backend.common.config import get_settings

_pool: ConnectionPool | None = None
_SCHEMA_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


def build_conninfo() -> str:
    settings = get_settings()
    if not _SCHEMA_NAME.match(settings.db_schema):
        raise ValueError(f"DB_SCHEMA 값이 올바르지 않습니다: {settings.db_schema!r}")
    return psycopg.conninfo.make_conninfo(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        options=f"-c search_path={settings.db_schema} -c timezone=Asia/Seoul",
        application_name="c-maker",
    )


def open_pool() -> ConnectionPool:
    """프로세스당 1회 호출한다. 이미 열려 있으면 기존 풀을 반환한다."""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            conninfo=build_conninfo(),
            min_size=settings.db_pool_min_size,
            max_size=settings.db_pool_max_size,
            kwargs={"row_factory": dict_row},
            open=True,
        )
        _pool.wait(timeout=10)
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """풀에서 커넥션을 빌린다. 블록이 예외 없이 끝나면 commit, 예외면 rollback된다."""
    pool = open_pool()
    with pool.connection() as conn:
        yield conn
