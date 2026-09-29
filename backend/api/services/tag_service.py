"""1클릭 태깅 (UC-09, VAL-06, RULE-LEARN-01/02).

- 태깅은 RM이 소속 지점 추천에 대해서만 한다.
- 부적합(REJECTED)은 사유 4종 중 정확히 1개 필수, 그 외 태깅은 사유를 받지 않는다.
- 재태깅은 기존 행 갱신, 되돌리기는 태깅 삭제(미태깅 복귀). 모든 변경은 감사 로그에 남긴다(REQ-15).
- 태깅 데이터는 신호 가중치 학습 외 용도(개인·지점 성과 평가)로 쓰지 않는다(CLAUDE.md §0.7).
"""

from __future__ import annotations

import psycopg

from backend.api.middlewares.error_middleware import NotFoundError, ValidationFailedError
from backend.api.repositories import audit_repository, recommendation_repository, tag_repository
from backend.api.services.recommendation_service import require_branch
from backend.common.schemas.auth import CurrentUser
from backend.common.schemas.recommendation import TagRequest, TagResponse


def _load_owned(conn: psycopg.Connection, user: CurrentUser, recommendation_id: int) -> None:
    branch_id = require_branch(user)
    row = recommendation_repository.get_recommendation(conn, recommendation_id)
    if row is None or row["branch_id"] != branch_id:
        raise NotFoundError("추천 항목을 찾을 수 없습니다.")


def _snapshot(tag: dict | None) -> dict | None:
    return None if tag is None else {"tag_value": tag["tag_value"], "reject_reason": tag["reject_reason"]}


def save_tag(conn: psycopg.Connection, user: CurrentUser, recommendation_id: int, request: TagRequest) -> TagResponse:
    if request.tag_status == "REJECTED" and request.rejected_reason is None:
        raise ValidationFailedError("부적합 사유를 선택해주세요.", code="REJECT_REASON_REQUIRED")
    if request.tag_status != "REJECTED" and request.rejected_reason is not None:
        raise ValidationFailedError("부적합이 아닌 태깅에는 사유를 지정할 수 없습니다.")

    _load_owned(conn, user, recommendation_id)
    before = tag_repository.get_tag(conn, recommendation_id)
    tag_repository.upsert_tag(conn, recommendation_id, user.id, request.tag_status, request.rejected_reason)
    audit_repository.insert(
        conn, actor_user_id=user.id, action="TAG_SAVED", entity_type="recommendation",
        entity_id=str(recommendation_id), before_value=_snapshot(before),
        after_value={"tag_value": request.tag_status, "reject_reason": request.rejected_reason},
    )
    return TagResponse(recommendation_id=recommendation_id, tag_status=request.tag_status,
                       rejected_reason=request.rejected_reason)


def remove_tag(conn: psycopg.Connection, user: CurrentUser, recommendation_id: int) -> TagResponse:
    _load_owned(conn, user, recommendation_id)
    before = tag_repository.get_tag(conn, recommendation_id)
    if before is not None:
        tag_repository.delete_tag(conn, recommendation_id)
        audit_repository.insert(
            conn, actor_user_id=user.id, action="TAG_REVERTED", entity_type="recommendation",
            entity_id=str(recommendation_id), before_value=_snapshot(before), after_value=None,
        )
    return TagResponse(recommendation_id=recommendation_id, tag_status="UNTAGGED", rejected_reason=None)
