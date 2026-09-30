"""배치 전용 SQL 모음.

판정·채점 로직(sensing/targeting)은 DB를 모르는 순수 함수로 두고(PRIN-08 재현성, TEST-01/02),
배치 진입점이 이 모듈로 입력을 읽고 결과를 적재한다. 모든 함수는 호출자가 넘긴 커넥션(트랜잭션)을 쓴다.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import psycopg
from pydantic import BaseModel

from backend.common.geo import bounding_box
from backend.common.schemas.branch import BranchContext
from backend.common.schemas.brief import BriefContent
from backend.common.schemas.business import BusinessCandidate, BusinessRecord, TagHistoryEntry
from backend.common.schemas.event import ActiveEvent, ExistingEvent
from backend.common.schemas.recommendation import RankedRecommendation
from backend.common.schemas.signal import SignalDraft, SignalWeightEntry


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


# ─────────────────────────── 설정 파라미터 ───────────────────────────


class ThresholdParam(BaseModel):
    id: int
    signal_type: str
    category: str
    threshold_value: float
    unit: str
    updated_at: datetime


def load_thresholds(conn: psycopg.Connection) -> dict[str, ThresholdParam]:
    rows = conn.execute(
        "SELECT id, signal_type, category, threshold_value, unit, updated_at FROM threshold_config"
    ).fetchall()
    return {row["signal_type"]: ThresholdParam.model_validate(row) for row in rows}


def load_signal_weights(conn: psycopg.Connection) -> list[SignalWeightEntry]:
    rows = conn.execute(
        "SELECT signal_type, industry_code, weight, alpha, beta, sample_count FROM signal_weight ORDER BY id"
    ).fetchall()
    return [SignalWeightEntry.model_validate(row) for row in rows]


# ─────────────────────────── 지점 ───────────────────────────

_BRANCH_COLUMNS = """
    b.id, b.branch_code,
    CASE WHEN use_hist THEN h.name ELSE b.name END AS name,
    CASE WHEN use_hist THEN h.address ELSE b.address END AS address,
    CASE WHEN use_hist THEN h.lat ELSE b.lat END AS lat,
    CASE WHEN use_hist THEN h.lng ELSE b.lng END AS lng,
    CASE WHEN use_hist THEN h.coverage_radius_km ELSE b.coverage_radius_km END AS coverage_radius_km,
    CASE WHEN use_hist THEN h.primary_industry_tags ELSE b.primary_industry_tags END AS primary_industry_tags,
    CASE WHEN use_hist THEN h.handles_forex ELSE b.handles_forex END AS handles_forex,
    CASE WHEN use_hist THEN h.atm_count ELSE b.atm_count END AS atm_count,
    use_hist AS from_history
"""


def _to_branch(row: dict[str, Any]) -> BranchContext:
    tags = [tag.strip() for tag in (row["primary_industry_tags"] or "").split(",") if tag.strip()]
    return BranchContext.model_validate({**row, "primary_industry_tags": tags})


def load_effective_branches(conn: psycopg.Connection, reference_ts: datetime) -> list[BranchContext]:
    """RULE-BRANCH-01: 기준 시각(당일 07:30)에 효력이 있는 지점 값.
    effective_from이 기준 시각 이후면 BRANCH_HISTORY의 옛 값을 쓰고, 옛 값도 없으면(당일 신규 등록) 제외한다."""
    rows = conn.execute(
        f"""
        SELECT {_BRANCH_COLUMNS}
        FROM branch b
        LEFT JOIN LATERAL (
            SELECT *
            FROM branch_history bh
            WHERE bh.branch_id = b.id AND bh.valid_from <= %(ref)s AND bh.valid_until > %(ref)s
            ORDER BY bh.valid_until DESC, bh.id DESC
            LIMIT 1
        ) h ON b.effective_from > %(ref)s
        CROSS JOIN LATERAL (SELECT b.effective_from > %(ref)s AS use_hist) flags
        WHERE b.effective_from <= %(ref)s OR h.id IS NOT NULL
        ORDER BY b.id
        """,
        {"ref": reference_ts},
    ).fetchall()
    return [_to_branch(row) for row in rows]


def load_current_branches(conn: psycopg.Connection) -> list[BranchContext]:
    """모집단 적재(월간)는 온보딩 직후에도 돌 수 있도록 현재 값 기준으로 범위를 잡는다."""
    rows = conn.execute(
        """
        SELECT id, branch_code, name, address, lat, lng, coverage_radius_km, primary_industry_tags,
               handles_forex, atm_count, FALSE AS from_history
        FROM branch
        ORDER BY id
        """
    ).fetchall()
    return [_to_branch(row) for row in rows]


def load_branches_to_geocode(conn: psycopg.Connection) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT id, branch_code, address
        FROM branch
        WHERE lat IS NULL OR lng IS NULL OR geocoded_address IS DISTINCT FROM address
        ORDER BY id
        """
    ).fetchall()


def update_branch_coordinates(conn: psycopg.Connection, branch_id: int, address: str, lat: float, lng: float) -> bool:
    """주소가 조회 시점과 같을 때만 갱신한다. 트리거가 이력·effective_from을 처리한다(CONST-19)."""
    cursor = conn.execute(
        """
        UPDATE branch SET lat = %s, lng = %s, geocoded_address = address
        WHERE id = %s AND address = %s
        """,
        (lat, lng, branch_id, address),
    )
    return cursor.rowcount == 1


# ─────────────────────────── 사업체 (모집단) ───────────────────────────


def find_businesses_in_box(
    conn: psycopg.Connection, min_lat: float, max_lat: float, min_lng: float, max_lng: float
) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT id, permit_mgt_no, sbiz_store_id, name, industry_code, industry_name, address,
               lat::float8 AS lat, lng::float8 AS lng, biz_reg_no, operating_status, status_source, licensed_on,
               population_as_of
        FROM business
        WHERE lat BETWEEN %s AND %s AND lng BETWEEN %s AND %s
        """,
        (min_lat, max_lat, min_lng, max_lng),
    ).fetchall()


def find_business_by_permit_no(conn: psycopg.Connection, permit_mgt_no: str) -> dict[str, Any] | None:
    return conn.execute(
        "SELECT id, status_source, biz_reg_no FROM business WHERE permit_mgt_no = %s", (permit_mgt_no,)
    ).fetchone()


def upsert_business_by_permit(conn: psycopg.Connection, record: BusinessRecord, merge_into_id: int | None) -> int:
    """CONST-13: 인허가 관리번호로 병합한다. 국세청(NTS) 조회로 갱신된 상태는 인허가 값이 덮어쓰지 않는다(RULE-TARGET-01)."""
    params = record.model_dump()
    if merge_into_id is not None:
        # 상가정보로 먼저 적재된 같은 사업체에 인허가 관리번호를 붙인다(좌표·상호 기준 매칭).
        conn.execute(
            """
            UPDATE business SET
                permit_mgt_no = %(permit_mgt_no)s,
                licensed_on = COALESCE(%(licensed_on)s, licensed_on),
                operating_status = CASE WHEN status_source = 'NTS' THEN operating_status ELSE %(operating_status)s END,
                status_source = CASE WHEN status_source = 'NTS' THEN status_source ELSE 'PERMIT' END,
                status_checked_at = CURRENT_DATE,
                population_as_of = %(population_as_of)s,
                updated_at = now()
            WHERE id = %(merge_into_id)s
            """,
            {**params, "merge_into_id": merge_into_id},
        )
        return merge_into_id

    row = conn.execute(
        """
        INSERT INTO business (permit_mgt_no, name, industry_code, industry_name, address, lat, lng, source_crs,
                              biz_reg_no, operating_status, status_source, licensed_on, status_checked_at, population_as_of)
        VALUES (%(permit_mgt_no)s, %(name)s, %(industry_code)s, %(industry_name)s, %(address)s, %(lat)s, %(lng)s,
                %(source_crs)s, %(biz_reg_no)s, %(operating_status)s, 'PERMIT', %(licensed_on)s, CURRENT_DATE,
                %(population_as_of)s)
        ON CONFLICT (permit_mgt_no) DO UPDATE SET
            name = EXCLUDED.name,
            industry_code = EXCLUDED.industry_code,
            industry_name = EXCLUDED.industry_name,
            address = COALESCE(EXCLUDED.address, business.address),
            lat = EXCLUDED.lat,
            lng = EXCLUDED.lng,
            source_crs = EXCLUDED.source_crs,
            licensed_on = COALESCE(EXCLUDED.licensed_on, business.licensed_on),
            operating_status = CASE WHEN business.status_source = 'NTS' THEN business.operating_status
                                    ELSE EXCLUDED.operating_status END,
            status_source = CASE WHEN business.status_source = 'NTS' THEN business.status_source ELSE 'PERMIT' END,
            status_checked_at = CURRENT_DATE,
            population_as_of = EXCLUDED.population_as_of,
            updated_at = now()
        RETURNING id
        """,
        params,
    ).fetchone()
    assert row is not None
    return int(row["id"])


def update_business_status_by_permit(
    conn: psycopg.Connection, permit_mgt_no: str, operating_status: str, checked_on: date
) -> int | None:
    """변동분(폐업·휴업 등)으로 기존 사업체 상태만 갱신한다. NTS 확인값은 덮어쓰지 않는다."""
    row = conn.execute(
        """
        UPDATE business SET operating_status = %s, status_source = 'PERMIT', status_checked_at = %s, updated_at = now()
        WHERE permit_mgt_no = %s AND status_source <> 'NTS'
        RETURNING id
        """,
        (operating_status, checked_on, permit_mgt_no),
    ).fetchone()
    return int(row["id"]) if row else None


def upsert_business_by_sbiz(conn: psycopg.Connection, record: BusinessRecord) -> int:
    row = conn.execute(
        """
        INSERT INTO business (sbiz_store_id, name, industry_code, industry_name, address, lat, lng, source_crs,
                              operating_status, status_source, status_checked_at, population_as_of)
        VALUES (%(sbiz_store_id)s, %(name)s, %(industry_code)s, %(industry_name)s, %(address)s, %(lat)s, %(lng)s,
                %(source_crs)s, '정상', 'SBIZ', CURRENT_DATE, %(population_as_of)s)
        ON CONFLICT (sbiz_store_id) DO UPDATE SET
            name = EXCLUDED.name,
            industry_code = CASE WHEN business.permit_mgt_no IS NULL THEN EXCLUDED.industry_code ELSE business.industry_code END,
            industry_name = CASE WHEN business.permit_mgt_no IS NULL THEN EXCLUDED.industry_name ELSE business.industry_name END,
            address = COALESCE(EXCLUDED.address, business.address),
            lat = EXCLUDED.lat,
            lng = EXCLUDED.lng,
            source_crs = EXCLUDED.source_crs,
            -- 인허가·국세청이 판정한 상태는 상가정보가 덮어쓰지 않는다.
            operating_status = CASE WHEN business.status_source = 'SBIZ' THEN '정상' ELSE business.operating_status END,
            status_checked_at = CURRENT_DATE,
            population_as_of = EXCLUDED.population_as_of,
            updated_at = now()
        RETURNING id
        """,
        record.model_dump(),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def mark_sbiz_missing_closed(
    conn: psycopg.Connection, candidate_ids: list[int], seen_ids: set[int], checked_on: date
) -> int:
    """직전 적재에는 있었지만 이번 상가정보(영업 중 업소 전수)에 없는 SBIZ 출처 사업체를 폐업으로 표시한다.
    인허가·국세청 출처 상태는 건드리지 않는다. 명부 내 휴폐업 0건(MVP 종료 조건)을 보수적으로 지키기 위함."""
    missing = [business_id for business_id in candidate_ids if business_id not in seen_ids]
    if not missing:
        return 0
    cursor = conn.execute(
        """
        UPDATE business SET operating_status = '폐업', status_checked_at = %s, updated_at = now()
        WHERE id = ANY(%s) AND status_source = 'SBIZ' AND operating_status = '정상'
        """,
        (checked_on, missing),
    )
    return cursor.rowcount


def list_biz_reg_nos_in_box(
    conn: psycopg.Connection, min_lat: float, max_lat: float, min_lng: float, max_lng: float
) -> tuple[list[str], int]:
    """(국세청 조회 대상 사업자번호, 사업자번호가 없어 조회를 생략한 건수)."""
    rows = conn.execute(
        """
        SELECT biz_reg_no FROM business
        WHERE lat BETWEEN %s AND %s AND lng BETWEEN %s AND %s AND operating_status <> '폐업'
        """,
        (min_lat, max_lat, min_lng, max_lng),
    ).fetchall()
    numbers = sorted({row["biz_reg_no"] for row in rows if row["biz_reg_no"]})
    missing = sum(1 for row in rows if not row["biz_reg_no"])
    return numbers, missing


def update_business_status_by_nts(
    conn: psycopg.Connection, biz_reg_no: str, operating_status: str, checked_on: date
) -> int:
    cursor = conn.execute(
        """
        UPDATE business SET operating_status = %s, status_source = 'NTS', status_checked_at = %s, updated_at = now()
        WHERE biz_reg_no = %s
        """,
        (operating_status, checked_on, biz_reg_no),
    )
    return cursor.rowcount


# ─────────────────────────── 배치 실행 이력 ───────────────────────────


def fail_stale_runs(conn: psycopg.Connection, stale_minutes: int) -> int:
    cursor = conn.execute(
        """
        UPDATE batch_run SET status = 'FAILED', completed_at = now(),
               failure_reason = '비정상 종료로 판단되어 실패 처리됨(RUNNING 상태 장기 지속)'
        WHERE status = 'RUNNING' AND COALESCE(started_at, requested_at) < now() - make_interval(mins => %s)
        """,
        (stale_minutes,),
    )
    return cursor.rowcount


def create_scheduled_run(conn: psycopg.Connection, target_date: date) -> int | None:
    """CONST-17: 이미 RUNNING인 실행이 있으면 새 실행을 만들지 않는다(부분 유니크 인덱스가 보장)."""
    row = conn.execute(
        """
        INSERT INTO batch_run (run_type, status, target_date, started_at)
        VALUES ('SCHEDULED', 'RUNNING', %s, now())
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        (target_date,),
    ).fetchone()
    return int(row["id"]) if row else None


def get_run(conn: psycopg.Connection, run_id: int) -> dict[str, Any] | None:
    return conn.execute(
        "SELECT id, run_type, status, triggered_by, target_date, requested_at FROM batch_run WHERE id = %s",
        (run_id,),
    ).fetchone()


def mark_run_started(conn: psycopg.Connection, run_id: int) -> None:
    conn.execute("UPDATE batch_run SET started_at = COALESCE(started_at, now()) WHERE id = %s", (run_id,))


def finish_run(
    conn: psycopg.Connection,
    run_id: int,
    *,
    status: str,
    failure_reason: str | None,
    params_snapshot: dict[str, Any],
    stage_stats: dict[str, Any],
    source_status: list[dict[str, Any]],
) -> bool:
    cursor = conn.execute(
        """
        UPDATE batch_run SET status = %s, completed_at = now(), failure_reason = %s,
               params_snapshot = %s::jsonb, stage_stats = %s::jsonb, source_status = %s::jsonb
        WHERE id = %s AND status = 'RUNNING'
        """,
        (status, failure_reason, _json(params_snapshot), _json(stage_stats), _json(source_status), run_id),
    )
    return cursor.rowcount > 0


def insert_audit(
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
        (
            actor_user_id,
            action,
            entity_type,
            entity_id,
            None if before_value is None else _json(before_value),
            None if after_value is None else _json(after_value),
        ),
    )


# ─────────────────────────── 신호·이벤트 ───────────────────────────


def load_cooldown_events(conn: psycopg.Connection, branch_id: int, since: date) -> list[ExistingEvent]:
    rows = conn.execute(
        """
        SELECT id, signal_type, target_key,
               GREATEST(occurred_on, COALESCE(last_merged_on, occurred_on)) AS occurred_on
        FROM event
        WHERE branch_id = %s AND status = 'ACTIVE'
          AND GREATEST(occurred_on, COALESCE(last_merged_on, occurred_on)) >= %s
        ORDER BY GREATEST(occurred_on, COALESCE(last_merged_on, occurred_on)) DESC, id DESC
        """,
        (branch_id, since),
    ).fetchall()
    return [ExistingEvent.model_validate(row) for row in rows]


def count_active_events_on(conn: psycopg.Connection, branch_id: int, day: date) -> int:
    row = conn.execute(
        "SELECT count(*) AS n FROM event WHERE branch_id = %s AND occurred_on = %s AND status = 'ACTIVE'",
        (branch_id, day),
    ).fetchone()
    return int(row["n"]) if row else 0


def insert_signal(
    conn: psycopg.Connection, draft: SignalDraft, batch_run_id: int | None, event_id: int | None
) -> int | None:
    """같은 스냅샷에서 이미 만든 신호는 다시 만들지 않는다(재실행 멱등성). 새로 만든 경우에만 ID를 돌려준다."""
    detail = {**draft.detail, "source_name": draft.source_name}
    if draft.industry_name:
        detail["industry_name"] = draft.industry_name
    row = conn.execute(
        """
        INSERT INTO signal (snapshot_id, branch_id, business_id, signal_type, scope, target_key, intensity,
                            raw_value, unit, detail, as_of_date, event_id, batch_run_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
        ON CONFLICT (snapshot_id, branch_id, signal_type, target_key) DO NOTHING
        RETURNING id
        """,
        (
            draft.snapshot_id,
            draft.branch_id,
            draft.business_id,
            draft.signal_type,
            draft.scope,
            draft.target_key,
            round(draft.intensity, 3),
            draft.raw_value,
            draft.unit,
            _json(detail),
            draft.as_of_date,
            event_id,
            batch_run_id,
        ),
    ).fetchone()
    return int(row["id"]) if row else None


def signal_exists(conn: psycopg.Connection, draft: SignalDraft) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM signal WHERE snapshot_id = %s AND branch_id = %s AND signal_type = %s AND target_key = %s
        """,
        (draft.snapshot_id, draft.branch_id, draft.signal_type, draft.target_key),
    ).fetchone()
    return row is not None


def insert_event(
    conn: psycopg.Connection,
    *,
    branch_id: int,
    draft: SignalDraft,
    promotion_reason: str,
    occurred_on: date,
    score: float,
    status: str,
    batch_run_id: int | None,
) -> int:
    row = conn.execute(
        """
        INSERT INTO event (branch_id, signal_type, scope, target_key, promotion_reason, occurred_on, as_of_date,
                           score, status, batch_run_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            branch_id,
            draft.signal_type,
            draft.scope,
            draft.target_key,
            promotion_reason,
            occurred_on,
            draft.as_of_date,
            round(score, 4),
            status,
            batch_run_id,
        ),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def mark_event_merged(conn: psycopg.Connection, event_id: int, merged_on: date, as_of_date: date) -> None:
    conn.execute(
        "UPDATE event SET last_merged_on = %s, as_of_date = GREATEST(as_of_date, %s) WHERE id = %s",
        (merged_on, as_of_date, event_id),
    )


def load_scoring_events(conn: psycopg.Connection, branch_id: int, since: date, until: date) -> list[ActiveEvent]:
    """스코어링 입력: 최근 활동일(발생·병합)이 기간 안인 ACTIVE 이벤트와 그 최신 신호."""
    rows = conn.execute(
        """
        SELECT DISTINCT ON (e.id)
               e.id AS event_id, e.signal_type, e.scope, e.target_key, s.business_id,
               s.detail->>'industry_name' AS industry_name,
               s.intensity::float8 AS intensity, s.raw_value::float8 AS raw_value, s.unit, s.as_of_date,
               COALESCE(s.detail->>'source_name', '') AS source_name, s.detail
        FROM event e
        JOIN signal s ON s.event_id = e.id
        WHERE e.branch_id = %s AND e.status = 'ACTIVE'
          AND GREATEST(e.occurred_on, COALESCE(e.last_merged_on, e.occurred_on)) BETWEEN %s AND %s
        ORDER BY e.id, s.as_of_date DESC, s.id DESC
        """,
        (branch_id, since, until),
    ).fetchall()
    return [ActiveEvent.model_validate(row) for row in rows]


# ─────────────────────────── 명부 (targeting) ───────────────────────────


def load_candidates(conn: psycopg.Connection, branch: BranchContext) -> list[dict[str, Any]]:
    """담당 반경을 감싸는 위경도 박스 안의 사업체(1차 필터). 정밀 반경 판정은 호출 측이 하버사인으로 한다."""
    assert branch.lat is not None and branch.lng is not None
    min_lat, max_lat, min_lng, max_lng = bounding_box(branch.lat, branch.lng, branch.coverage_radius_km)
    return find_businesses_in_box(conn, min_lat, max_lat, min_lng, max_lng)


def load_tag_history(conn: psycopg.Connection, business_ids: list[int]) -> list[TagHistoryEntry]:
    if not business_ids:
        return []
    rows = conn.execute(
        """
        SELECT r.business_id, t.tag_value, t.reject_reason, (t.tagged_at AT TIME ZONE 'Asia/Seoul')::date AS tagged_on
        FROM tag_feedback t
        JOIN recommendation r ON r.id = t.recommendation_id
        WHERE r.business_id = ANY(%s)
        """,
        (business_ids,),
    ).fetchall()
    return [TagHistoryEntry.model_validate(row) for row in rows]


def load_last_exposure(conn: psycopg.Connection, branch_id: int, business_ids: list[int], before: date) -> dict[int, date]:
    if not business_ids:
        return {}
    rows = conn.execute(
        """
        SELECT business_id, max(recommended_on) AS last_on
        FROM recommendation
        WHERE branch_id = %s AND business_id = ANY(%s) AND recommended_on < %s
        GROUP BY business_id
        """,
        (branch_id, business_ids, before),
    ).fetchall()
    return {int(row["business_id"]): row["last_on"] for row in rows}


def branch_has_tagged_recommendations(conn: psycopg.Connection, branch_id: int, day: date) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM recommendation r JOIN tag_feedback t ON t.recommendation_id = r.id
        WHERE r.branch_id = %s AND r.recommended_on = %s LIMIT 1
        """,
        (branch_id, day),
    ).fetchone()
    return row is not None


def count_missing_branch_briefs(conn: psycopg.Connection, branch_id: int, day: date) -> int:
    row = conn.execute(
        """
        SELECT count(*) AS missing_count
        FROM recommendation r
        LEFT JOIN brief b ON b.recommendation_id = r.id
        WHERE r.branch_id = %s AND r.recommended_on = %s AND b.recommendation_id IS NULL
        """,
        (branch_id, day),
    ).fetchone()
    return int(row["missing_count"]) if row else 0


def count_brief_completeness(conn: psycopg.Connection, recommendation_ids: list[int]) -> tuple[int, int]:
    """새 추천 ID 집합과 BRIEF의 1:1 저장 여부를 같은 트랜잭션에서 검증한다."""
    if not recommendation_ids:
        return 0, 0
    row = conn.execute(
        """
        SELECT count(DISTINCT r.id) AS recommendation_count,
               count(DISTINCT b.recommendation_id) AS brief_count
        FROM recommendation r
        LEFT JOIN brief b ON b.recommendation_id = r.id
        WHERE r.id = ANY(%s)
        """,
        (recommendation_ids,),
    ).fetchone()
    if row is None:
        return 0, 0
    return int(row["recommendation_count"]), int(row["brief_count"])


def delete_recommendations(conn: psycopg.Connection, branch_id: int, day: date) -> int:
    cursor = conn.execute(
        "DELETE FROM recommendation WHERE branch_id = %s AND recommended_on = %s", (branch_id, day)
    )
    return cursor.rowcount


def insert_recommendation(
    conn: psycopg.Connection,
    *,
    branch_id: int,
    day: date,
    ranked: RankedRecommendation,
    batch_run_id: int | None,
) -> int:
    candidate = ranked.candidate
    score_detail = {
        "contributions": [item.model_dump() for item in candidate.contributions],
        "freshness": candidate.freshness_detail,
    }
    row = conn.execute(
        """
        INSERT INTO recommendation (branch_id, business_id, score, signal_score, freshness_score, proximity,
                                    scale_fit, distance_km, reason_tier, rank_in_branch, is_exploration_slot,
                                    recommended_on, batch_run_id, score_detail)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id
        """,
        (
            branch_id,
            candidate.business_id,
            round(candidate.score, 4),
            round(candidate.signal_score, 4),
            round(candidate.freshness_score, 3),
            round(candidate.proximity, 3),
            round(candidate.scale_fit, 3),
            round(candidate.distance_km, 2),
            candidate.reason_tier,
            ranked.rank,
            ranked.is_exploration_slot,
            day,
            batch_run_id,
            _json(score_detail),
        ),
    ).fetchone()
    assert row is not None
    recommendation_id = int(row["id"])
    event_ids = sorted({item.event_id for item in candidate.contributions if item.contribution > 0})
    for event_id in event_ids:
        conn.execute(
            "INSERT INTO recommendation_event (recommendation_id, event_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (recommendation_id, event_id),
        )
    return recommendation_id


def insert_brief(conn: psycopg.Connection, content: BriefContent) -> None:
    citation_tags = sorted({(fact.source_name, fact.as_of_date) for fact in content.reason_facts})
    conn.execute(
        """
        INSERT INTO brief (recommendation_id, reason_summary, reason_facts, talk_script, checklist, citation_tags,
                           generation_status, validation_errors, prompt, model_version, raw_output, latency_ms)
        VALUES (%s, %s, %s::jsonb, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s, %s, %s)
        ON CONFLICT (recommendation_id) DO UPDATE SET
            reason_summary = EXCLUDED.reason_summary, reason_facts = EXCLUDED.reason_facts,
            talk_script = EXCLUDED.talk_script, checklist = EXCLUDED.checklist,
            citation_tags = EXCLUDED.citation_tags, generation_status = EXCLUDED.generation_status,
            validation_errors = EXCLUDED.validation_errors, prompt = EXCLUDED.prompt,
            model_version = EXCLUDED.model_version, raw_output = EXCLUDED.raw_output,
            latency_ms = EXCLUDED.latency_ms, generated_at = now()
        """,
        (
            content.recommendation_id,
            content.reason_summary,
            _json([{"text": fact.text, "sourceTag": fact.source_tag} for fact in content.reason_facts]),
            "\n".join(content.talk_script),
            "\n".join(content.checklist),
            _json([list(tag) for tag in citation_tags]),
            content.generation_status,
            _json(content.validation_errors),
            content.prompt,
            content.model_version,
            content.raw_output,
            content.latency_ms,
        ),
    )


def to_candidate(row: dict[str, Any], distance_km: float) -> BusinessCandidate:
    return BusinessCandidate.model_validate({**row, "distance_km": distance_km})
