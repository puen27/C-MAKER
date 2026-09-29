"""개발용 픽스처 제거 — load_dev_fixture.py로 넣은 임시 데이터와 그 데이터로 돌린 배치 결과를 지운다.

⚠ APP_ENV=dev 에서만 실행된다. 운영 DB에 쓰지 않는다.
   seed.sql 데이터(지점·계정·임계치·가중치)와 audit_log는 건드리지 않는다.

지우는 대상 (한 트랜잭션, 실패 시 전부 롤백)
1. 스냅샷: request_params.dev_fixture = true
2. 사업체: 상호가 '(개발용)'으로 끝나는 행(가상 사업체 30곳 + 인허가 픽스처로 들어온 신규 개업)
3. 배치 실행: source_status에 픽스처 스냅샷을 쓴 실행, 또는 픽스처 사업체를 추천한 실행
4. 위 1~3에서 파생된 추천(브리프·사유 이벤트 CASCADE)·태깅·신호·이벤트
5. 지점 000101 좌표: 픽스처가 넣은 값 그대로일 때만 NULL로 되돌린다(지오코딩 전 상태)

실행: APP_ENV=dev python -m backend.scripts.clear_dev_fixture [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal

import psycopg

from backend.common.config import get_settings
from backend.common.db.pool import close_pool, get_connection
from backend.scripts.load_dev_fixture import BRANCH_CODE, BRANCH_LAT, BRANCH_LNG

FIXTURE_NAME_PATTERN = "%(개발용)"


def _ids(conn: psycopg.Connection, sql: str, params: tuple = ()) -> list[int]:
    return [row["id"] for row in conn.execute(sql, params).fetchall()]


def _delete(conn: psycopg.Connection, sql: str, params: tuple) -> int:
    return conn.execute(sql, params).rowcount


def clear(conn: psycopg.Connection) -> dict[str, int]:
    snapshot_ids = _ids(conn, "SELECT id FROM data_source_snapshot WHERE request_params->>'dev_fixture' = 'true'")
    business_ids = _ids(conn, "SELECT id FROM business WHERE name LIKE %s", (FIXTURE_NAME_PATTERN,))
    run_ids = _ids(
        conn,
        """
        SELECT id FROM batch_run br
        WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(br.source_status) s
                      WHERE (s->>'snapshot_id')::int = ANY(%s))
           OR EXISTS (SELECT 1 FROM recommendation r
                      WHERE r.batch_run_id = br.id AND r.business_id = ANY(%s))
        """,
        (snapshot_ids, business_ids),
    )
    recommendation_ids = _ids(
        conn,
        "SELECT id FROM recommendation WHERE business_id = ANY(%s) OR batch_run_id = ANY(%s)",
        (business_ids, run_ids),
    )
    signal_filter = "snapshot_id = ANY(%s) OR business_id = ANY(%s) OR batch_run_id = ANY(%s)"
    signal_params = (snapshot_ids, business_ids, run_ids)
    event_ids = sorted(
        set(_ids(conn, f"SELECT DISTINCT event_id AS id FROM signal WHERE event_id IS NOT NULL AND ({signal_filter})",
                 signal_params))
        | set(_ids(conn, "SELECT id FROM event WHERE batch_run_id = ANY(%s)", (run_ids,)))
    )

    counts: dict[str, int] = {}
    # tag_feedback은 추천 삭제 시 CASCADE가 없으므로 먼저 지운다(schema.sql §12).
    counts["tag_feedback"] = _delete(conn, "DELETE FROM tag_feedback WHERE recommendation_id = ANY(%s)",
                                     (recommendation_ids,))
    # brief·recommendation_event는 CASCADE로 함께 지워진다.
    counts["recommendation"] = _delete(conn, "DELETE FROM recommendation WHERE id = ANY(%s)", (recommendation_ids,))
    counts["signal"] = _delete(conn, f"DELETE FROM signal WHERE {signal_filter}", signal_params)
    counts["event"] = _delete(
        conn,
        """
        DELETE FROM event e WHERE e.id = ANY(%s)
          AND NOT EXISTS (SELECT 1 FROM signal s WHERE s.event_id = e.id)
          AND NOT EXISTS (SELECT 1 FROM recommendation_event re WHERE re.event_id = e.id)
        """,
        (event_ids,),
    )
    counts["data_source_snapshot"] = _delete(
        conn,
        """
        DELETE FROM data_source_snapshot d WHERE d.id = ANY(%s)
          AND NOT EXISTS (SELECT 1 FROM signal s WHERE s.snapshot_id = d.id)
        """,
        (snapshot_ids,),
    )
    counts["business"] = _delete(
        conn,
        """
        DELETE FROM business b WHERE b.id = ANY(%s)
          AND NOT EXISTS (SELECT 1 FROM recommendation r WHERE r.business_id = b.id)
          AND NOT EXISTS (SELECT 1 FROM signal s WHERE s.business_id = b.id)
        """,
        (business_ids,),
    )
    counts["batch_run"] = _delete(
        conn,
        """
        DELETE FROM batch_run br WHERE br.id = ANY(%s)
          AND NOT EXISTS (SELECT 1 FROM recommendation r WHERE r.batch_run_id = br.id)
          AND NOT EXISTS (SELECT 1 FROM signal s WHERE s.batch_run_id = br.id)
          AND NOT EXISTS (SELECT 1 FROM event e WHERE e.batch_run_id = br.id)
        """,
        (run_ids,),
    )
    counts["branch_coordinates_reset"] = reset_branch(conn)
    return counts


def reset_branch(conn: psycopg.Connection) -> int:
    """픽스처가 넣은 좌표 그대로일 때만 되돌린다(실제 지오코딩 결과는 보존)."""
    row = conn.execute("SELECT lat, lng FROM branch WHERE branch_code = %s", (BRANCH_CODE,)).fetchone()
    if row is None or row["lat"] != Decimal(f"{BRANCH_LAT:.7f}") or row["lng"] != Decimal(f"{BRANCH_LNG:.7f}"):
        return 0
    # load_dev_fixture와 같은 이유로 트리거를 잠시 끈다(branch_history에 가짜 이력을 남기지 않기 위함).
    conn.execute("ALTER TABLE branch DISABLE TRIGGER trg_branch_effective_from")
    updated = conn.execute(
        "UPDATE branch SET lat = NULL, lng = NULL, geocoded_address = NULL WHERE branch_code = %s", (BRANCH_CODE,)
    ).rowcount
    conn.execute("ALTER TABLE branch ENABLE TRIGGER trg_branch_effective_from")
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="개발용 픽스처 제거")
    parser.add_argument("--dry-run", action="store_true", help="지울 건수만 출력하고 롤백한다")
    args = parser.parse_args(argv)

    if not get_settings().is_dev:
        print("APP_ENV=dev 에서만 실행할 수 있습니다(운영 DB 보호).", file=sys.stderr)
        return 2
    try:
        with get_connection() as conn:
            counts = clear(conn)
            if args.dry_run:
                conn.rollback()
        label = "삭제 예정(dry-run, 롤백됨)" if args.dry_run else "개발용 픽스처 제거 완료"
        print(f"{label}: " + ", ".join(f"{name} {count}" for name, count in counts.items()))
        return 0
    finally:
        close_pool()


if __name__ == "__main__":
    sys.exit(main())
