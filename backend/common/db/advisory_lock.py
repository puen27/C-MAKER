"""배치 데이터 변경의 PostgreSQL session advisory lock.

세션 잠금은 트랜잭션 잠금과 달리 커넥션에 귀속된다. 공용 풀을 점유하면 잠금 본문이
pool size=1에서 재진입할 때 교착될 수 있으므로, 잠금 수명 전체에 direct autocommit
커넥션을 전용으로 사용한다. 잠금 DB 오류는 경쟁으로 간주하지 않고 호출자에게 전파한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from backend.common.db.pool import build_conninfo

# 0x434D414B4552는 ASCII "CMAKER" namespace다. 하위 16bit로 작업군을 분리해
# 다른 애플리케이션 advisory lock과 우연히 충돌할 가능성을 낮춘 signed bigint 키다.
BATCH_MUTATION_LOCK_KEY = 0x434D414B45520001
GEOCODE_LOCK_KEY = 0x434D414B45520002


@contextmanager
def acquire_advisory_lock_connection(lock_key: int) -> Iterator[tuple[bool, psycopg.Connection]]:
    """전용 direct connection에서 session lock을 획득하고 같은 세션과 함께 반환한다.

    autocommit이므로 이 커넥션에서 수행하는 stale 정리 같은 쓰기는 unlock 전에 확정된다.
    """
    acquired = False
    with psycopg.connect(build_conninfo(), autocommit=True, row_factory=dict_row) as conn:
        row = conn.execute(
            "SELECT pg_try_advisory_lock(%s) AS acquired",
            (lock_key,),
        ).fetchone()
        if row is None or "acquired" not in row:
            raise RuntimeError("advisory lock 조회 결과가 올바르지 않습니다.")
        acquired = bool(row["acquired"])
        try:
            yield acquired, conn
        finally:
            if acquired:
                conn.execute("SELECT pg_advisory_unlock(%s) AS released", (lock_key,))


@contextmanager
def acquire_advisory_lock(lock_key: int) -> Iterator[bool]:
    """기존 bool context API를 유지하는 session advisory lock 진입점."""
    with acquire_advisory_lock_connection(lock_key) as (acquired, _conn):
        yield acquired
