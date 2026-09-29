"""임계치·운영 파라미터 관리 (REQ-14, UC-15, VAL-05, REQ-15 이력).

변경은 즉시 저장되고 다음 배치부터 적용된다(배치는 실행 시작 시 THRESHOLD_CONFIG를 읽는다).
"""

from __future__ import annotations

import math

import psycopg

from backend.api.middlewares.error_middleware import NotFoundError, ValidationFailedError
from backend.api.repositories import audit_repository, threshold_repository
from backend.common.schemas.auth import CurrentUser
from backend.common.schemas.threshold import ThresholdHistoryItem, ThresholdUpdateRequest, ThresholdView


def list_thresholds(conn: psycopg.Connection) -> list[ThresholdView]:
    return [ThresholdView.model_validate(row) for row in threshold_repository.list_all(conn)]


def validate_value(row: dict, request: ThresholdUpdateRequest) -> float:
    """VAL-05: 0 이상의 수치, 대상 지표 단위와 일치. 고정 항목·정수 항목·허용 범위도 검증한다."""
    if row["is_fixed"]:
        raise ValidationFailedError(f"'{row['label']}'은(는) 고정 항목이라 변경할 수 없습니다.", code="FIXED_THRESHOLD")
    value = request.threshold_value
    if not math.isfinite(value):
        raise ValidationFailedError("임계치는 숫자여야 합니다.")
    if value < 0:
        raise ValidationFailedError("임계치는 0 이상이어야 합니다.")
    if request.unit is not None and request.unit != row["unit"]:
        raise ValidationFailedError(f"단위가 일치하지 않습니다(허용 단위: {row['unit']}).", code="UNIT_MISMATCH")
    if row["integer_only"] and not float(value).is_integer():
        raise ValidationFailedError(f"'{row['label']}'은(는) 정수만 입력할 수 있습니다.")
    if row["min_value"] is not None and value < row["min_value"]:
        raise ValidationFailedError(f"허용 범위보다 작습니다(최소 {row['min_value']:g}{row['unit']}).")
    if row["max_value"] is not None and value > row["max_value"]:
        raise ValidationFailedError(f"허용 범위보다 큽니다(최대 {row['max_value']:g}{row['unit']}).")
    return float(value)


def update_threshold(
    conn: psycopg.Connection, user: CurrentUser, threshold_id: int, request: ThresholdUpdateRequest
) -> ThresholdView:
    row = threshold_repository.get(conn, threshold_id, for_update=True)
    if row is None:
        raise NotFoundError("임계치 항목을 찾을 수 없습니다.")
    value = validate_value(row, request)
    if value != row["threshold_value"]:
        threshold_repository.update_value(conn, threshold_id, value, user.id)
        audit_repository.insert(
            conn, actor_user_id=user.id, action="THRESHOLD_UPDATED", entity_type="threshold_config",
            entity_id=str(threshold_id),
            before_value={"threshold_value": row["threshold_value"], "unit": row["unit"]},
            after_value={"threshold_value": value, "unit": row["unit"]},
        )
    updated = threshold_repository.get(conn, threshold_id)
    assert updated is not None
    return ThresholdView.model_validate(updated)


def threshold_history(conn: psycopg.Connection, threshold_id: int) -> list[ThresholdHistoryItem]:
    if threshold_repository.get(conn, threshold_id) is None:
        raise NotFoundError("임계치 항목을 찾을 수 없습니다.")
    return [
        ThresholdHistoryItem(
            id=row["id"], changed_by_name=row["actor_name"], changed_at=row["created_at"],
            before_value=row["before_value"], after_value=row["after_value"],
        )
        for row in audit_repository.list_for_entity(conn, "threshold_config", str(threshold_id))
    ]
