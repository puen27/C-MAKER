"""지방행정 인허가 원본 행 → PermitRecord.

전수 CSV(한글 표준 컬럼명), 신규 업종별 API(대문자 스네이크, api/11-api-spec.md §1.5),
구 LOCALDATA API(camelCase — 이전 스냅샷 폴백용)를 같은 형태로 옮긴다.
신규 API에는 업종 식별자가 없어 커넥터가 호출 업종의 opnSvcId/opnSvcNm을 행에 붙여 준다.
좌표는 원본(EPSG:5174) 그대로 두며, WGS84 변환은 호출 측이 common/geo로 수행한다(VAL-11).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from backend.common.schemas.business import OperatingStatus, PermitRecord

# 공통 필드 → 후보 키 (CSV 한글 컬럼, 신규 API 대문자 스네이크, 구 API camelCase)
_FIELD_KEYS: dict[str, tuple[str, ...]] = {
    "mgt_no": ("관리번호", "MNG_NO", "mgtNo", "MGTNO"),
    "name": ("사업장명", "BPLC_NM", "bplcNm", "BPLCNM"),
    "service_name": ("개방서비스명", "opnSvcNm", "OPNSVCNM"),
    "service_id": ("개방서비스아이디", "opnSvcId", "OPNSVCID"),
    "uptae": ("업태구분명", "BZSTAT_SE_NM", "uptaeNm", "UPTAENM"),
    "status_code": ("영업상태구분코드", "SALS_STTS_CD", "trdStateGbn", "TRDSTATEGBN"),
    "status_name": ("영업상태명", "SALS_STTS_NM", "trdStateNm", "TRDSTATENM"),
    "detail_status_name": ("상세영업상태명", "DTL_SALS_STTS_NM", "dtlStateNm", "DTLSTATENM"),
    "licensed_on": ("인허가일자", "LCPMT_YMD", "apvPermYmd", "APVPERMYMD"),
    "closed_on": ("폐업일자", "CLSBIZ_YMD", "dcbYmd", "DCBYMD"),
    "road_address": ("도로명전체주소", "ROAD_NM_ADDR", "rdnWhlAddr", "RDNWHLADDR"),
    "site_address": ("소재지전체주소", "LOTNO_ADDR", "siteWhlAddr", "SITEWHLADDR"),
    "update_type": ("데이터갱신구분", "DAT_UPDT_SE", "updateGbn", "UPDATEGBN"),
}
_X_KEYS = ("좌표정보(x)", "좌표정보(X)", "좌표정보x(epsg5174)", "CRD_INFO_X", "x", "X")
_Y_KEYS = ("좌표정보(y)", "좌표정보(Y)", "좌표정보y(epsg5174)", "CRD_INFO_Y", "y", "Y")
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
    if code in ("04", "05", "06"):  # 04 취소/말소/만료/정지/중지, 05 제외/삭제/전출, 06 기타 — 모두 영업 대상 아님
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


def is_excluded_permit(record: PermitRecord, keywords: Iterable[str]) -> bool:
    """공공 보건기관 등 영업 대상이 아닌 인허가(api/11-api-spec.md §1.9).

    업태(industry_name)에 키워드가 들어 있거나 사업장명이 키워드로 끝나면 제외한다.
    사업장명은 접미만 본다 — '○○보건소앞약국' 같은 상호를 잘못 거르지 않기 위해서다.
    """
    name = record.name.strip()
    return any(keyword and (keyword in record.industry_name or name.endswith(keyword)) for keyword in keywords)
