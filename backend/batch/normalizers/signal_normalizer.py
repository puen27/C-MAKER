"""소스별 원본 → SIGNAL 정규화 (기준일·사유 범위 scope 부여, RULE-TARGET-06).

모든 함수는 DB를 모르는 순수 함수다. 입력은 스냅샷 원본(또는 그로부터 확정된 값), 출력은 SignalDraft 목록.
한 지점·한 번의 정규화에서 (signal_type, target_key)는 중복되지 않는다.

raw_value는 THRESHOLD_CONFIG와 비교하는 값(같은 단위), intensity는 스코어링용 0~1 정규화값이다.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from backend.common.config import NormalizationConfig, PipelineConfig
from backend.common.geo import extract_sido, haversine_km
from backend.common.schemas.branch import BranchContext
from backend.common.schemas.signal import SignalDraft

_TARGET_KEY_MAX = 80


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _key(prefix: str, value: str = "") -> str:
    return f"{prefix}:{value}"[:_TARGET_KEY_MAX] if value else prefix


# ─────────────────────────── 지방행정 인허가 신규 개업 ───────────────────────────


@dataclass(frozen=True)
class OpeningInfo:
    """변동분에서 확인된 신규 개업 사업체(BUSINESS 적재 후 ID가 확정된 값)."""

    business_id: int
    name: str
    industry_name: str
    licensed_on: date
    lat: float
    lng: float


def normalize_permit_openings(
    branch: BranchContext,
    openings: list[OpeningInfo],
    *,
    snapshot_id: int,
    as_of_date: date,
    config: NormalizationConfig,
) -> list[SignalDraft]:
    if not branch.has_coordinates:
        return []
    in_radius = [
        opening
        for opening in openings
        if haversine_km(branch.lat, branch.lng, opening.lat, opening.lng) <= branch.coverage_radius_km  # type: ignore[arg-type]
    ]
    if not in_radius:
        return []

    source = "PERMIT_DAILY"
    signals: list[SignalDraft] = []
    for opening in sorted(in_radius, key=lambda item: item.business_id):
        age_days = max(0, (as_of_date - opening.licensed_on).days)
        intensity = _clip01(max(0.3, 1 - age_days / max(config.new_opening_max_age_days, 1)))
        signals.append(
            SignalDraft(
                snapshot_id=snapshot_id,
                source_name=source,
                branch_id=branch.id,
                business_id=opening.business_id,
                signal_type="NEW_BUSINESS_OPENING",
                scope="BUSINESS",
                target_key=_key("BUSINESS", str(opening.business_id)),
                intensity=round(intensity, 3),
                raw_value=1,
                unit="건",
                as_of_date=as_of_date,
                detail={
                    "business_name": opening.name,
                    "industry_name": opening.industry_name,
                    "licensed_on": opening.licensed_on.isoformat(),
                },
            )
        )

    count = len(in_radius)
    signals.append(
        SignalDraft(
            snapshot_id=snapshot_id,
            source_name=source,
            branch_id=branch.id,
            signal_type="AREA_NEW_OPENINGS",
            scope="AREA",
            target_key="AREA",
            intensity=round(_clip01(count / config.area_openings_saturation), 3),
            raw_value=count,
            unit="건/일",
            as_of_date=as_of_date,
            detail={"count": count, "radius_km": branch.coverage_radius_km},
        )
    )

    by_industry: dict[str, int] = defaultdict(int)
    for opening in in_radius:
        if opening.industry_name:
            by_industry[opening.industry_name] += 1
    for industry_name, industry_count in sorted(by_industry.items()):
        signals.append(
            SignalDraft(
                snapshot_id=snapshot_id,
                source_name=source,
                branch_id=branch.id,
                signal_type="INDUSTRY_NEW_OPENINGS",
                scope="INDUSTRY",
                target_key=_key("INDUSTRY", industry_name),
                intensity=round(_clip01(industry_count / config.industry_openings_saturation), 3),
                raw_value=industry_count,
                unit="건/일",
                as_of_date=as_of_date,
                detail={"count": industry_count, "industry_name": industry_name,
                        "radius_km": branch.coverage_radius_km},
                industry_name=industry_name,
            )
        )
    return signals


# ─────────────────────────── 기상청 특보 ───────────────────────────

# 예: "[특보] 제05-12호 : 2026.08.25.10:00 / 폭염주의보 발효(*)", "호우주의보 해제, 강풍주의보 발효"
_WARNING_PATTERN = re.compile(r"([가-힣]+?)(주의보|경보)\s*(발효|변경|대치|연장|해제)")
_ACTIVE_ACTIONS = {"발효", "변경", "대치", "연장"}


def _parse_tm(value: Any) -> datetime | None:
    """발표시각 tmFc(YYYYMMDDHHMM 숫자)를 datetime으로."""
    digits = re.sub(r"\D", "", str(value or ""))
    try:
        if len(digits) >= 12:
            return datetime.strptime(digits[:12], "%Y%m%d%H%M")
        if len(digits) >= 8:
            return datetime.strptime(digits[:8], "%Y%m%d")
    except ValueError:
        return None
    return None


def normalize_weather_warnings(
    branch: BranchContext,
    payload: dict[str, Any],
    *,
    snapshot_id: int,
    config: PipelineConfig,
) -> list[SignalDraft]:
    """지점 소재 시도의 발표 관서 특보. 발효·변경은 raw=1(승격 대상), 해제는 raw=0(원장에만 저장)."""
    sido = extract_sido(branch.address)
    station_id = config.kma_station_by_sido.get(sido or "")
    if station_id is None:
        return []
    items = (payload.get("stations") or {}).get(str(station_id), [])

    latest: dict[str, tuple[datetime, int, str, str]] = {}  # warning → (시각, 발표순번, 조치, 수준)
    for item in items:
        issued_at = _parse_tm(item.get("tmFc"))
        if issued_at is None:
            continue
        sequence = int(item.get("tmSeq") or 0)
        for kind, level, action in _WARNING_PATTERN.findall(str(item.get("title") or "")):
            warning = f"{kind}{level}"
            current = latest.get(warning)
            if current is None or (issued_at, sequence) > (current[0], current[1]):
                latest[warning] = (issued_at, sequence, action, level)

    norm = config.normalization
    signals: list[SignalDraft] = []
    for warning, (issued_at, _sequence, action, level) in sorted(latest.items()):
        active = action in _ACTIVE_ACTIONS
        base = norm.warning_intensity_alert if level == "경보" else norm.warning_intensity_advisory
        signals.append(
            SignalDraft(
                snapshot_id=snapshot_id,
                source_name="KMA_WARNING",
                branch_id=branch.id,
                signal_type="WEATHER_WARNING",
                scope="AREA",
                target_key=_key("WEATHER", warning),
                intensity=round(base if active else 0.0, 3),
                raw_value=1 if active else 0,
                unit="건",
                as_of_date=issued_at.date(),
                detail={"warning": warning, "level": level, "action": action, "sido": sido,
                        "station_id": station_id, "issued_at": issued_at.isoformat(timespec="minutes")},
            )
        )
    return signals


# ─────────────────────────── 한국은행 ECOS 환율 ───────────────────────────


def compute_fx_change(payload: dict[str, Any]) -> dict[str, Any] | None:
    """가장 최근 두 영업일 매매기준율의 변동률. 계산할 수 없으면 None."""
    points: list[tuple[date, float]] = []
    for row in payload.get("rows") or []:
        try:
            day = datetime.strptime(str(row.get("TIME")), "%Y%m%d").date()
            value = float(str(row.get("DATA_VALUE")).replace(",", ""))
        except (TypeError, ValueError):
            continue
        points.append((day, value))
    points.sort()
    if len(points) < 2 or points[-2][1] == 0:
        return None
    (prev_day, prev_rate), (last_day, last_rate) = points[-2], points[-1]
    change_pct = (last_rate - prev_rate) / prev_rate * 100
    return {"as_of": last_day, "rate": last_rate, "prev_rate": prev_rate, "prev_date": prev_day.isoformat(),
            "change_pct": round(change_pct, 4)}


def normalize_fx(
    branch: BranchContext, fx: dict[str, Any], *, snapshot_id: int, config: NormalizationConfig
) -> list[SignalDraft]:
    change = float(fx["change_pct"])
    return [
        SignalDraft(
            snapshot_id=snapshot_id,
            source_name="ECOS_FX",
            branch_id=branch.id,
            signal_type="FX_DAILY_CHANGE",
            scope="INDUSTRY",
            target_key="MACRO:FX",
            intensity=round(_clip01(abs(change) / config.fx_change_saturation_pct), 3),
            raw_value=round(abs(change), 4),
            unit="%",
            as_of_date=fx["as_of"],
            detail={"rate": fx["rate"], "prev_rate": fx["prev_rate"], "prev_date": fx["prev_date"],
                    "change_pct": change},
        )
    ]


# ─────────────────────────── 오피넷 유가 ───────────────────────────


def normalize_oil_price(
    branch: BranchContext,
    payload: dict[str, Any],
    *,
    snapshot_id: int,
    as_of_date: date,
    config: PipelineConfig,
) -> list[SignalDraft]:
    """지점 소재 시도의 평균 가격 전일 대비 변동률(시도 단위 → 지점 상권 매핑)."""
    sido = extract_sido(branch.address)
    code = config.opinet_sido_code.get(sido or "")
    if code is None:
        return []
    row = next((item for item in payload.get("oil") or [] if str(item.get("SIDOCD")) == code), None)
    if row is None:
        return []
    try:
        price = float(row.get("PRICE"))
        diff = float(row.get("DIFF"))
    except (TypeError, ValueError):
        return []
    prev_price = price - diff
    if prev_price <= 0:
        return []
    change = diff / prev_price * 100
    return [
        SignalDraft(
            snapshot_id=snapshot_id,
            source_name="OPINET_PRICE",
            branch_id=branch.id,
            signal_type="OIL_PRICE_CHANGE",
            scope="INDUSTRY",
            target_key="MACRO:OIL",
            intensity=round(_clip01(abs(change) / config.normalization.oil_change_saturation_pct), 3),
            raw_value=round(abs(change), 4),
            unit="%",
            as_of_date=as_of_date,
            detail={"sido": sido, "price": price, "diff": diff, "change_pct": round(change, 4),
                    "prodcd": payload.get("prodcd")},
        )
    ]
