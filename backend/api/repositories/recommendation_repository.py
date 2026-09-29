from __future__ import annotations

from datetime import date
from typing import Any

import psycopg


def previous_list_date(conn: psycopg.Connection, branch_id: int, day: date) -> date | None:
    """직전 명부 일자(주말·휴일로 비는 날을 건너뛴 '어제'의 의미, UC-09 예외 흐름)."""
    row = conn.execute(
        "SELECT max(recommended_on) AS day FROM recommendation WHERE branch_id = %s AND recommended_on < %s",
        (branch_id, day),
    ).fetchone()
    return row["day"] if row else None


def list_for_branch(
    conn: psycopg.Connection, branch_id: int, day: date, previous_day: date | None
) -> list[dict[str, Any]]:
    return conn.execute(
        """
        SELECT r.id, r.rank_in_branch AS rank, b.name AS business_name, b.industry_name AS industry,
               r.score::float8 AS score, br.reason_summary, br.reason_facts->0->>'sourceTag' AS reason_source_tag,
               t.tag_value, t.reject_reason,
               EXISTS (
                   SELECT 1 FROM recommendation y
                   LEFT JOIN tag_feedback yt ON yt.recommendation_id = y.id
                   WHERE y.branch_id = r.branch_id AND y.business_id = r.business_id
                     AND y.recommended_on = %(previous_day)s AND yt.id IS NULL
               ) AS carried_over
        FROM recommendation r
        JOIN business b ON b.id = r.business_id
        LEFT JOIN brief br ON br.recommendation_id = r.id
        LEFT JOIN tag_feedback t ON t.recommendation_id = r.id
        WHERE r.branch_id = %(branch_id)s AND r.recommended_on = %(day)s
        ORDER BY r.rank_in_branch
        """,
        {"branch_id": branch_id, "day": day, "previous_day": previous_day},
    ).fetchall()


def count_list(conn: psycopg.Connection, branch_id: int, day: date) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE t.id IS NULL) AS untagged,
               count(*) FILTER (WHERE r.reason_tier = 'AREA') AS area_only
        FROM recommendation r
        LEFT JOIN tag_feedback t ON t.recommendation_id = r.id
        WHERE r.branch_id = %s AND r.recommended_on = %s
        """,
        (branch_id, day),
    ).fetchone()
    return {key: int(row[key]) for key in ("total", "untagged", "area_only")} if row else {
        "total": 0, "untagged": 0, "area_only": 0}


def count_events(conn: psycopg.Connection, branch_id: int, day: date) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT count(*) FILTER (WHERE status = 'ACTIVE') AS active,
               count(*) FILTER (WHERE status = 'TRIMMED') AS trimmed
        FROM event WHERE branch_id = %s AND occurred_on = %s
        """,
        (branch_id, day),
    ).fetchone()
    return {"active": int(row["active"]), "trimmed": int(row["trimmed"])} if row else {"active": 0, "trimmed": 0}


def get_recommendation(conn: psycopg.Connection, recommendation_id: int) -> dict[str, Any] | None:
    return conn.execute(
        "SELECT id, branch_id, business_id, recommended_on FROM recommendation WHERE id = %s",
        (recommendation_id,),
    ).fetchone()


def get_brief_detail(conn: psycopg.Connection, recommendation_id: int) -> dict[str, Any] | None:
    return conn.execute(
        """
        SELECT r.id, r.branch_id, r.recommended_on, r.distance_km::float8 AS distance_km,
               b.name AS business_name, b.industry_name, b.address,
               br.reason_summary, br.reason_facts, br.talk_script, br.checklist, br.generation_status,
               t.tag_value, t.reject_reason
        FROM recommendation r
        JOIN business b ON b.id = r.business_id
        LEFT JOIN brief br ON br.recommendation_id = r.id
        LEFT JOIN tag_feedback t ON t.recommendation_id = r.id
        WHERE r.id = %s
        """,
        (recommendation_id,),
    ).fetchone()


def export_rows(conn: psycopg.Connection, branch_id: int, day: date) -> list[dict[str, Any]]:
    """CRM 등록 파일 행. 영업상태 '정상'만 포함한다(crm-integration.md §6)."""
    return conn.execute(
        """
        SELECT r.rank_in_branch AS rank, b.name AS business_name, b.industry_name, b.address, b.biz_reg_no,
               b.operating_status, br.reason_summary, br.reason_facts->0->>'sourceTag' AS source_tag,
               r.recommended_on, bc.branch_code
        FROM recommendation r
        JOIN business b ON b.id = r.business_id
        JOIN branch bc ON bc.id = r.branch_id
        LEFT JOIN brief br ON br.recommendation_id = r.id
        WHERE r.branch_id = %s AND r.recommended_on = %s AND b.operating_status = '정상'
        ORDER BY r.rank_in_branch
        """,
        (branch_id, day),
    ).fetchall()


def branch_code(conn: psycopg.Connection, branch_id: int) -> str | None:
    row = conn.execute("SELECT branch_code FROM branch WHERE id = %s", (branch_id,)).fetchone()
    return row["branch_code"] if row else None


def has_list(conn: psycopg.Connection, day: date, branch_id: int | None) -> bool:
    if branch_id is None:
        row = conn.execute("SELECT 1 FROM recommendation WHERE recommended_on = %s LIMIT 1", (day,)).fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM recommendation WHERE recommended_on = %s AND branch_id = %s LIMIT 1", (day, branch_id)
        ).fetchone()
    return row is not None
