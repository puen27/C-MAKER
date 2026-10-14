"""API 도메인 규칙 단위 테스트 — VAL-05(임계치), VAL-06(부적합 사유), 공통 에러 형식, CSV 수식 주입 방지."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.middlewares.error_middleware import ValidationFailedError
from backend.api.services import tag_service
from backend.api.services.recommendation_service import _cell
from backend.api.services.threshold_service import validate_value
from backend.common.schemas.auth import CurrentUser
from backend.common.schemas.recommendation import TagRequest
from backend.common.schemas.threshold import ThresholdUpdateRequest

ROW = {"label": "신규 개업(상권)", "unit": "건/일", "is_fixed": False, "integer_only": True,
       "min_value": 0.0, "max_value": 1000.0}


def test_threshold_accepts_valid_value():
    assert validate_value(ROW, ThresholdUpdateRequest(threshold_value=5)) == 5


@pytest.mark.parametrize(("value", "unit", "code"), [
    (-1, None, "VALIDATION_ERROR"),       # SC-04 예외 흐름: 음수
    (2.5, None, "VALIDATION_ERROR"),      # 정수 항목
    (5000, None, "VALIDATION_ERROR"),     # 범위 초과
    (5, "%", "UNIT_MISMATCH"),            # 단위 불일치
])
def test_threshold_rejects_invalid_value(value, unit, code):
    with pytest.raises(ValidationFailedError) as exc:
        validate_value(ROW, ThresholdUpdateRequest(threshold_value=value, unit=unit))
    assert exc.value.code == code


def test_fixed_threshold_cannot_be_changed():
    with pytest.raises(ValidationFailedError) as exc:
        validate_value({**ROW, "is_fixed": True}, ThresholdUpdateRequest(threshold_value=1))
    assert exc.value.code == "FIXED_THRESHOLD"


def test_rejected_tag_requires_reason_before_touching_db():
    user = CurrentUser(id=1, role="RM", branch_id=1)
    with pytest.raises(ValidationFailedError) as exc:
        tag_service.save_tag(None, user, 1, TagRequest(tag_status="REJECTED"))  # type: ignore[arg-type]
    assert exc.value.code == "REJECT_REASON_REQUIRED"
    with pytest.raises(ValidationFailedError):
        tag_service.save_tag(None, user, 1, TagRequest(tag_status="VISITED", rejected_reason="NOT_TARGET"))  # type: ignore[arg-type]


def test_tag_request_accepts_camel_case_json():
    request = TagRequest.model_validate({"tagStatus": "REJECTED", "rejectedReason": "NOT_TARGET"})
    assert request.rejected_reason == "NOT_TARGET"


def test_csv_formula_injection_is_neutralized():
    assert _cell("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert _cell("정상 상호") == "정상 상호"
    assert _cell(None) == ""


def test_crm_row_follows_crm_register_columns_and_product_mapping():
    from datetime import date

    from backend.api.services.recommendation_service import CRM_COLUMNS, _crm_row

    row = _crm_row({
        "business_name": "가나다 카페", "consulted_on": date(2026, 10, 14), "signal_type": "NEW_BUSINESS_OPENING",
        "reason_summary": "10월 8일 인허가, 개업 6일째 — 첫 거래를 만들 적기",
        "source_tag": "지방행정인허가·2026-10-12", "branch_code": "000101",
    })
    assert [label for label, _key in CRM_COLUMNS] == [
        "사업자등록번호", "상호명", "상담일자", "고객관리유형", "상세유형", "채널", "유입경로", "추진상품", "내용", "등록사무소코드"]
    assert row["biz_reg_no_blank"] == ""
    assert (row["care_type"], row["channel"], row["inflow"]) == ("상품추진", "방문", "신규(가망)고객")
    assert row["detail_type"] == "수신추진"
    assert row["crm_products"] == "수신, 전자금융, 카드"
    assert row["content"] == "[NH Campaigner] 10월 8일 인허가, 개업 6일째 — 첫 거래를 만들 적기 [지방행정인허가·2026-10-12]"
    long_row = _crm_row({"reason_summary": "가" * 2000, "signal_type": None})
    assert len(long_row["content"]) == 1000


def test_products_for_falls_back_to_default_for_no_signal_rows():
    """10/14 테스트 결과 9번: 가까운 거리(신호 없음) 행도 CRM 상세유형·추진상품이 비지 않는다."""
    from backend.api.services.recommendation_service import _crm_row
    from backend.common.config import get_pipeline_config

    config = get_pipeline_config()
    for signal_type in (None, "", "UNKNOWN_SIGNAL"):
        mapping = config.products_for(signal_type)
        assert mapping is not None
        assert (mapping.detail_type, mapping.crm_products, mapping.brief_products) == (
            "수신추진", ["수신"], ["사업잘되는NH통장"])
    assert config.products_for("FX_DAILY_CHANGE").detail_type == "외환추진"
    row = _crm_row({"reason_summary": "지점에서 약 0.3km", "signal_type": None})
    assert (row["detail_type"], row["crm_products"]) == ("수신추진", "수신")


def test_unauthenticated_request_uses_common_error_format(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    from backend.api.app import create_app
    from backend.common.config import get_settings

    get_settings.cache_clear()
    # `with` 없이 쓰면 lifespan(DB 풀 생성)이 실행되지 않는다 — 라우팅·인증 계층만 검증한다.
    client = TestClient(create_app())
    response = client.get("/api/recommendations")
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "UNAUTHORIZED", "message": "로그인이 필요합니다."}}
    missing = client.get("/api/nothing-here")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "NOT_FOUND"
    get_settings.cache_clear()
