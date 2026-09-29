"""오늘의 접촉 TOP 20 조회(UC-06), 상담 브리프(UC-07), CRM 등록 파일(UC-08).

- RM·지점장은 소속 지점 데이터만 조회한다(VAL-08, OPS-03).
- 탐색 슬롯 여부는 응답에 싣지 않는다(RULE-TARGET-04).
- 순위·점수는 배치가 확정한 값을 그대로 읽는다. API는 재정렬·재채점을 하지 않는다.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any, Literal

import psycopg
from openpyxl import Workbook

from backend.api.middlewares.error_middleware import ForbiddenError, NotFoundError
from backend.api.repositories import audit_repository, recommendation_repository, threshold_repository
from backend.common.schemas.auth import CurrentUser
from backend.common.schemas.brief import BriefFactResponse, BriefResponse
from backend.common.schemas.recommendation import RecommendationItem, RecommendationSummary

DEFAULT_AREA_REASON_RATIO_LIMIT = 60.0
PENDING_REASON = "선정 사유 생성 중"


def require_branch(user: CurrentUser) -> int:
    if user.branch_id is None:
        raise ForbiddenError("지점 소속 계정만 조회할 수 있습니다.")
    return user.branch_id


def list_recommendations(conn: psycopg.Connection, user: CurrentUser, day: date) -> list[RecommendationItem]:
    branch_id = require_branch(user)
    previous_day = recommendation_repository.previous_list_date(conn, branch_id, day)
    rows = recommendation_repository.list_for_branch(conn, branch_id, day, previous_day)
    return [
        RecommendationItem(
            id=row["id"],
            rank=row["rank"],
            business_name=row["business_name"],
            industry=row["industry"] or "업종 미상",
            score=round(row["score"], 2),
            reason_summary=row["reason_summary"] or PENDING_REASON,
            reason_source_tag=row["reason_source_tag"] or "",
            tag_status=row["tag_value"] or "UNTAGGED",
            rejected_reason=row["reject_reason"],
            carried_over_from_yesterday=bool(row["carried_over"]) and row["tag_value"] is None,
        )
        for row in rows
    ]


def get_summary(conn: psycopg.Connection, user: CurrentUser, day: date) -> RecommendationSummary:
    branch_id = require_branch(user)
    counts = recommendation_repository.count_list(conn, branch_id, day)
    previous_day = recommendation_repository.previous_list_date(conn, branch_id, day)
    yesterday_untagged = (
        recommendation_repository.count_list(conn, branch_id, previous_day)["untagged"] if previous_day else 0
    )
    limit_row = threshold_repository.get_by_signal_type(conn, "AREA_REASON_RATIO_LIMIT")
    limit = float(limit_row["threshold_value"]) if limit_row else DEFAULT_AREA_REASON_RATIO_LIMIT
    # RULE-TARGET-06 상권사유비율: 사유 계층이 ③(AREA)만인 항목의 비율(%)
    ratio = round(counts["area_only"] / counts["total"] * 100, 1) if counts["total"] else 0.0
    events = recommendation_repository.count_events(conn, branch_id, day)
    return RecommendationSummary(
        date=day,
        total=counts["total"],
        untagged_count=counts["untagged"],
        yesterday_untagged_count=yesterday_untagged,
        area_reason_ratio=ratio,
        area_reason_ratio_limit=limit,
        area_reason_ratio_exceeded=counts["total"] > 0 and ratio > limit,
        active_event_count=events["active"],
        trimmed_event_count=events["trimmed"],
    )


def get_brief(conn: psycopg.Connection, user: CurrentUser, recommendation_id: int) -> BriefResponse:
    branch_id = require_branch(user)
    row = recommendation_repository.get_brief_detail(conn, recommendation_id)
    # 다른 지점 추천은 존재 여부도 드러내지 않는다.
    if row is None or row["branch_id"] != branch_id:
        raise NotFoundError("추천 항목을 찾을 수 없습니다.")
    facts = [
        BriefFactResponse(text=item.get("text", ""), source_tag=item.get("sourceTag", ""))
        for item in (row["reason_facts"] or [])
    ]
    return BriefResponse(
        recommendation_id=row["id"],
        business_name=row["business_name"],
        industry=row["industry_name"] or "업종 미상",
        address=row["address"],
        distance_label=f"지점에서 약 {row['distance_km']:.1f}km",
        recommended_on=row["recommended_on"].isoformat(),
        reason_facts=facts,
        script_lines=[line for line in (row["talk_script"] or "").splitlines() if line.strip()],
        checklist=[line for line in (row["checklist"] or "").splitlines() if line.strip()],
        generation_status=row["generation_status"] or "REASON_ONLY",
        tag_status=row["tag_value"] or "UNTAGGED",
        rejected_reason=row["reject_reason"],
    )


# ─────────────────────────── CRM 등록 파일 (REQ-07) ───────────────────────────

# ⚠ CRM 컬럼 매핑은 CRM팀 확인 전(CLAUDE.md §8-2). docs/crm-integration.md §3 잠정 컬럼을 따른다.
CRM_COLUMNS: list[tuple[str, str]] = [
    ("순위", "rank"),
    ("상호명", "business_name"),
    ("업종", "industry_name"),
    ("주소", "address"),
    ("사업자번호", "biz_reg_no"),
    ("영업상태", "operating_status"),
    ("선정사유", "reason_summary"),
    ("신호출처", "source_tag"),
    ("생성일", "recommended_on"),
    ("지점코드", "branch_code"),
]
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any) -> Any:
    """스프레드시트 수식 주입(CSV injection) 방지."""
    if value is None:
        return ""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def build_export(
    conn: psycopg.Connection, user: CurrentUser, day: date, file_format: Literal["csv", "xlsx"]
) -> tuple[bytes, str, str]:
    branch_id = require_branch(user)
    rows = recommendation_repository.export_rows(conn, branch_id, day)
    table = [[_cell(row[key]) for _label, key in CRM_COLUMNS] for row in rows]
    headers = [label for label, _key in CRM_COLUMNS]
    code = recommendation_repository.branch_code(conn, branch_id) or str(branch_id)
    filename = f"cmaker_{code}_{day.isoformat()}.{file_format}"

    if file_format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(table)
        content = buffer.getvalue().encode("utf-8-sig")  # Excel 호환 BOM
        media_type = "text/csv; charset=utf-8"
    else:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "접촉명부"
        sheet.append(headers)
        for line in table:
            sheet.append(line)
        output = io.BytesIO()
        workbook.save(output)
        content = output.getvalue()
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # crm-integration.md §6: 다운로드 이력을 감사 로그에 남긴다.
    audit_repository.insert(conn, actor_user_id=user.id, action="CRM_EXPORT", entity_type="recommendation_list",
                            entity_id=f"{branch_id}:{day.isoformat()}",
                            after_value={"format": file_format, "rows": len(table)})
    return content, filename, media_type
