"""지방행정 인허가 원본 행 → PermitRecord.

전수 CSV(한글 표준 컬럼명)와 변동분 API(camelCase 필드명)를 같은 형태로 옮긴다.
좌표는 원본(EPSG:5174) 그대로 두며, WGS84 변환은 호출 측이 common/geo로 수행한다(VAL-11).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from backend.common.schemas.business import OperatingStatus, PermitRecord

# 공통 필드 → 후보 키 (CSV 한글 컬럼, API camelCase)
_FIELD_KEYS: dict[str, tuple[str, ...]] = {
    "mgt_no": ("관리번호", "mgtNo", "MGTNO"),
    "name": ("사업장명", "bplcNm", "BPLCNM"),
    "service_name": ("개방서비스명", "opnSvcNm", "OPNSVCNM"),
    "service_id": ("개방서비스아이디", "opnSvcId", "OPNSVCID"),
    "uptae": ("업태구분명", "uptaeNm", "UPTAENM"),
    "status_code": ("영업상태구분코드", "trdStateGbn", "TRDSTATEGBN"),
    "status_name": ("영업상태명", "trdStateNm", "TRDSTATENM"),
    "detail_status_name": ("상세영업상태명", "dtlStateNm", "DTLSTATENM"),
    "licensed_on": ("인허가일자", "apvPermYmd", "APVPERMYMD"),
    "closed_on": ("폐업일자", "dcbYmd", "DCBYMD"),
    "road_address": ("도로명전체주소", "rdnWhlAddr", "RDNWHLADDR"),
    "site_address": ("소재지전체주소", "siteWhlAddr", "SITEWHLADDR"),
    "update_type": ("데이터갱신구분", "updateGbn", "UPDATEGBN"),
}
_X_KEYS = ("좌표정보(x)", "좌표정보(X)", "좌표정보x(epsg5174)", "x", "X")
_Y_KEYS = ("좌표정보(y)", "좌표정보(Y)", "좌표정보y(epsg5174)", "y", "Y")
_MEANINGLESS_UPTAE = {"", "기타", "-"}


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def parse_date(value: str) -> date | None:
    text = (value or "").strip().replace("-", "").replace(".", "")[:8]
    if len(text) != 8 or not text.isdigit():
        return None
    try:
        return datetime.strptime(text, "%Y%m%d").date()
    except ValueError:
        return None


def _parse_float(value: str) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None


def map_operating_status(code: str, name: str, detail_name: str) -> OperatingStatus | None:
    """인허가 영업상태 → BUSINESS.operating_status. 판별할 수 없으면 None(적재하지 않음)."""
    code = code.strip().zfill(2) if code.strip() else ""
    if "정지" in detail_name:
        return "영업정지"
    if code == "01":
        return "정상"
    if code == "02":
        return "휴업"
    if code == "03":
        return "폐업"
    if code == "04":  # 취소/말소/만료/정지/중지
        return "폐업"
    text = f"{name} {detail_name}"
    if "폐업" in text or "말소" in text or "취소" in text:
        return "폐업"
    if "휴업" in text:
        return "휴업"
    if "영업" in text or "정상" in text:
        return "정상"
    return None


def parse_permit_row(row: dict[str, Any]) -> PermitRecord | None:
    mgt_no = _pick(row, _FIELD_KEYS["mgt_no"])
    name = _pick(row, _FIELD_KEYS["name"])
    status = map_operating_status(
        _pick(row, _FIELD_KEYS["status_code"]),
        _pick(row, _FIELD_KEYS["status_name"]),
        _pick(row, _FIELD_KEYS["detail_status_name"]),
    )
    if not mgt_no or not name or status is None:
        return None

    service_name = _pick(row, _FIELD_KEYS["service_name"])
    uptae = _pick(row, _FIELD_KEYS["uptae"])
    industry_name = service_name
    if uptae not in _MEANINGLESS_UPTAE and uptae != service_name:
        industry_name = f"{service_name}·{uptae}" if service_name else uptae

    service_id = _pick(row, _FIELD_KEYS["service_id"])
    return PermitRecord(
        # 관리번호는 개방서비스별로 부여되므로 서비스 ID와 합쳐 전역 유일키로 쓴다(CONST-13).
        mgt_no=f"{service_id}-{mgt_no}" if service_id and not mgt_no.startswith(service_id) else mgt_no,
        name=name,
        industry_code=service_id,
        industry_name=industry_name[:100],
        operating_status=status,
        licensed_on=parse_date(_pick(row, _FIELD_KEYS["licensed_on"])),
        closed_on=parse_date(_pick(row, _FIELD_KEYS["closed_on"])),
        x=_parse_float(_pick(row, _X_KEYS)),
        y=_parse_float(_pick(row, _Y_KEYS)),
        address=(_pick(row, _FIELD_KEYS["road_address"]) or _pick(row, _FIELD_KEYS["site_address"]) or None),
        update_type=_pick(row, _FIELD_KEYS["update_type"]) or None,
    )
