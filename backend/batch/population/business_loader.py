"""사업체 모집단 적재 (REQ-16, UC-17).

- 소진공 상가(상권)정보(S-1): 지점 반경 내 영업 중 업소 전수, WGS84 좌표. 상가업소번호로 병합.
- 지방행정 인허가(F-2 전수 / N-1 변동분): EPSG:5174 → WGS84 변환 후(VAL-11) 인허가 관리번호로 병합(CONST-13).
  같은 사업체가 상가정보로 먼저 들어와 있으면 상호·좌표(50m 이내)로 찾아 관리번호를 붙인다.

적재 범위는 등록된 전 지점의 담당 반경으로 한정한다(UC-17 인수 기준 1).
병합은 기존 행 UPDATE이므로 BUSINESS.id가 유지되어 태깅 이력이 유실되지 않는다(UC-17 인수 기준 3).
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import psycopg

from backend.batch import batch_repository as repo
from backend.common.geo import PERMIT_SOURCE_CRS, WGS84, bounding_box, haversine_km, to_wgs84
from backend.common.schemas.branch import BranchContext
from backend.common.schemas.business import BusinessRecord, PermitRecord

logger = logging.getLogger(__name__)

SAME_BUSINESS_MAX_DISTANCE_KM = 0.05
_NAME_NOISE = re.compile(r"[\s()\[\]{}·\-_.,'\"/]+")


def normalize_name(name: str) -> str:
    return _NAME_NOISE.sub("", name).lower()


@dataclass
class AreaIndex:
    """전 지점 담당 반경의 합집합. 적재 대상 여부를 판정한다."""

    branches: list[BranchContext]

    def contains(self, lat: float, lng: float) -> bool:
        return any(
            haversine_km(b.lat, b.lng, lat, lng) <= b.coverage_radius_km  # type: ignore[arg-type]
            for b in self.branches
            if b.has_coordinates
        )

    def boxes(self) -> list[tuple[float, float, float, float]]:
        return [
            bounding_box(b.lat, b.lng, b.coverage_radius_km)  # type: ignore[arg-type]
            for b in self.branches
            if b.has_coordinates
        ]


# ─────────────────────────── 순수 변환 ───────────────────────────


def sbiz_item_to_record(item: dict[str, Any], population_as_of: date) -> BusinessRecord | None:
    store_id = str(item.get("bizesId") or "").strip()
    name = str(item.get("bizesNm") or "").strip()
    try:
        lat = float(item.get("lat"))  # type: ignore[arg-type]
        lng = float(item.get("lon"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not store_id or not name or to_wgs84(lng, lat, WGS84) is None:
        return None
    branch_name = str(item.get("brchNm") or "").strip()
    parts: list[str] = []
    for key in ("indsLclsNm", "indsMclsNm", "indsSclsNm"):
        value = str(item.get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    return BusinessRecord(
        sbiz_store_id=store_id,
        name=f"{name} {branch_name}".strip()[:200],
        industry_code=str(item.get("indsSclsCd") or item.get("indsMclsCd") or "")[:40],
        industry_name="·".join(parts)[:100],
        address=(str(item.get("rdnmAdr") or item.get("lnoAdr") or "").strip() or None),
        lat=round(lat, 7),
        lng=round(lng, 7),
        source_crs=WGS84,
        operating_status="정상",
        status_source="SBIZ",
        population_as_of=population_as_of,
    )


def permit_to_record(permit: PermitRecord, population_as_of: date) -> BusinessRecord | None:
    """VAL-11: 원본 좌표(EPSG:5174)를 WGS84로 변환한다. 좌표가 없거나 변환 결과가 국내 범위 밖이면 적재하지 않는다."""
    # 원본에 좌표가 비어 있으면 0으로 채워지는 경우가 있다 — 변환하지 않고 버린다.
    if permit.x is None or permit.y is None or permit.x <= 0 or permit.y <= 0:
        return None
    converted = to_wgs84(permit.x, permit.y, PERMIT_SOURCE_CRS)
    if converted is None:
        return None
    lat, lng = converted
    return BusinessRecord(
        permit_mgt_no=permit.mgt_no[:40],
        name=permit.name[:200],
        industry_code=permit.industry_code[:40],
        industry_name=permit.industry_name[:100],
        address=permit.address,
        lat=lat,
        lng=lng,
        source_crs=PERMIT_SOURCE_CRS,
        operating_status=permit.operating_status,
        status_source="PERMIT",
        licensed_on=permit.licensed_on,
        population_as_of=population_as_of,
    )


# ─────────────────────────── 적재 ───────────────────────────


@dataclass
class _SbizMatcher:
    """상가정보 출처(인허가 관리번호 없음) 사업체를 상호로 찾는다."""

    by_name: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: defaultdict(list))

    @classmethod
    def load(cls, conn: psycopg.Connection, area: AreaIndex) -> _SbizMatcher:
        matcher = cls()
        seen: set[int] = set()
        for box in area.boxes():
            for row in repo.find_businesses_in_box(conn, *box):
                if row["id"] in seen or row["permit_mgt_no"] is not None:
                    continue
                seen.add(row["id"])
                matcher.by_name[normalize_name(row["name"])].append(row)
        return matcher

    def take(self, record: BusinessRecord) -> int | None:
        rows = self.by_name.get(normalize_name(record.name), [])
        for row in rows:
            if haversine_km(row["lat"], row["lng"], record.lat, record.lng) <= SAME_BUSINESS_MAX_DISTANCE_KM:
                rows.remove(row)
                return int(row["id"])
        return None


@dataclass
class PermitApplyResult:
    upserted: int = 0
    status_updated: int = 0
    skipped_out_of_area: int = 0
    skipped_invalid: int = 0
    # (business_id, PermitRecord) — 일간 신규 개업 신호 입력
    new_openings: list[tuple[int, PermitRecord, BusinessRecord]] = field(default_factory=list)

    def as_dict(self) -> dict[str, int]:
        return {
            "upserted": self.upserted,
            "status_updated": self.status_updated,
            "skipped_out_of_area": self.skipped_out_of_area,
            "skipped_invalid": self.skipped_invalid,
            "new_openings": len(self.new_openings),
        }


def apply_permit_records(
    conn: psycopg.Connection,
    permits: Iterable[PermitRecord],
    area: AreaIndex,
    population_as_of: date,
    *,
    new_opening_since: date | None = None,
) -> PermitApplyResult:
    """인허가 레코드를 BUSINESS에 병합한다. `new_opening_since`가 주어지면 그 이후 인허가된 정상 영업 건을
    신규 개업으로 모아 돌려준다(일간 변동분용)."""
    result = PermitApplyResult()
    matcher = _SbizMatcher.load(conn, area)
    for permit in permits:
        record = permit_to_record(permit, population_as_of)
        if record is None:
            # 좌표가 없는 변동분(폐업 등)은 기존 행 상태만 갱신한다.
            if permit.operating_status != "정상" and repo.update_business_status_by_permit(
                conn, permit.mgt_no[:40], permit.operating_status, population_as_of
            ):
                result.status_updated += 1
            else:
                result.skipped_invalid += 1
            continue
        existing = repo.find_business_by_permit_no(conn, record.permit_mgt_no or "")
        # 반경 밖이라도 이미 적재된 사업체는 상태를 갱신한다(지점 반경 축소·이전 등).
        if existing is None and not area.contains(record.lat, record.lng):
            result.skipped_out_of_area += 1
            continue
        merge_into = None if existing else matcher.take(record)
        business_id = repo.upsert_business_by_permit(conn, record, merge_into)
        result.upserted += 1
        if (
            new_opening_since is not None
            and record.operating_status == "정상"
            and record.licensed_on is not None
            and record.licensed_on >= new_opening_since
        ):
            result.new_openings.append((business_id, permit, record))
    return result


class PopulationPublishError(RuntimeError):
    """완전한 모집단으로 안전하게 publish할 수 없을 때 발생한다."""


@dataclass
class SbizApplyResult:
    input_count: int
    unique_count: int
    upserted: int
    marked_closed: int
    existing_candidate_count: int
    incoming_count: int
    drop_ratio: float

    def as_dict(self) -> dict[str, int | float]:
        return {
            "input_count": self.input_count,
            "unique_count": self.unique_count,
            "upserted": self.upserted,
            "marked_closed": self.marked_closed,
            "existing_candidate_count": self.existing_candidate_count,
            "incoming_count": self.incoming_count,
            "drop_ratio": self.drop_ratio,
        }


def _validate_sbiz_publish_limits(
    min_population_records: int,
    max_population_drop_ratio: float,
) -> float:
    if (
        isinstance(min_population_records, bool)
        or not isinstance(min_population_records, int)
        or min_population_records < 1
    ):
        raise PopulationPublishError("min_population_records는 1 이상의 정수여야 합니다")
    if isinstance(max_population_drop_ratio, bool) or not isinstance(
        max_population_drop_ratio, (int, float)
    ):
        raise PopulationPublishError("max_population_drop_ratio는 0 이상 1 미만의 수여야 합니다")
    ratio = float(max_population_drop_ratio)
    if not 0 <= ratio < 1:
        raise PopulationPublishError("max_population_drop_ratio는 0 이상 1 미만이어야 합니다")
    return ratio


def apply_sbiz_records(
    conn: psycopg.Connection,
    items: Iterable[dict[str, Any]],
    area: AreaIndex,
    population_as_of: date,
    *,
    min_population_records: int,
    max_population_drop_ratio: float,
) -> SbizApplyResult:
    """전 지점 반경 합집합의 SBIZ 전수를 한 트랜잭션에서 fail-closed로 publish한다.

    모든 항목과 모집단 감소 폭을 먼저 검증해 가드가 실패하면 BUSINESS를 쓰지 않는다. 누락 폐업도
    지점별이 아니라 AreaIndex 전체의 기존 정상 SBIZ 후보와 전역 seen BUSINESS ID를 한 번만 비교한다.
    """
    allowed_drop_ratio = _validate_sbiz_publish_limits(
        min_population_records,
        max_population_drop_ratio,
    )
    source_items = list(items)
    records_by_store_id: dict[str, BusinessRecord] = {}
    invalid_count = 0
    for item in source_items:
        record = sbiz_item_to_record(item, population_as_of)
        if record is None or record.sbiz_store_id is None:
            invalid_count += 1
            continue
        previous = records_by_store_id.get(record.sbiz_store_id)
        if previous is not None and previous != record:
            raise PopulationPublishError(f"같은 bizesId의 SBIZ 레코드가 충돌합니다: {record.sbiz_store_id}")
        records_by_store_id[record.sbiz_store_id] = record

    if invalid_count:
        raise PopulationPublishError(f"SBIZ 변환 invalid 항목이 {invalid_count}건 있어 publish를 중단합니다")

    candidate_ids: set[int] = set()
    for box in area.boxes():
        for row in repo.find_businesses_in_box(conn, *box):
            business_id = int(row["id"])
            if (
                business_id in candidate_ids
                or row["sbiz_store_id"] is None
                or row["status_source"] != "SBIZ"
                or row["operating_status"] != "정상"
            ):
                continue
            if area.contains(float(row["lat"]), float(row["lng"])):
                candidate_ids.add(business_id)

    existing_candidate_count = len(candidate_ids)
    incoming_count = len(records_by_store_id)
    drop_ratio = (
        (existing_candidate_count - incoming_count) / existing_candidate_count
        if existing_candidate_count > 0
        else 0.0
    )
    if incoming_count < min_population_records:
        raise PopulationPublishError(
            "SBIZ incoming 모집단이 최소 건수보다 작아 publish를 중단합니다: "
            f"existing={existing_candidate_count}, incoming={incoming_count}, "
            f"drop_ratio={drop_ratio:.6f}, minimum={min_population_records}"
        )
    if existing_candidate_count > 0 and drop_ratio > allowed_drop_ratio:
        raise PopulationPublishError(
            "SBIZ 모집단 감소 비율이 허용치를 초과해 publish를 중단합니다: "
            f"existing={existing_candidate_count}, incoming={incoming_count}, "
            f"drop_ratio={drop_ratio:.6f}, maximum={allowed_drop_ratio:.6f}"
        )

    seen_business_ids = {
        repo.upsert_business_by_sbiz(conn, record) for record in records_by_store_id.values()
    }
    marked_closed = repo.mark_sbiz_missing_closed(
        conn,
        sorted(candidate_ids),
        seen_business_ids,
        population_as_of,
    )
    return SbizApplyResult(
        input_count=len(source_items),
        unique_count=incoming_count,
        upserted=incoming_count,
        marked_closed=marked_closed,
        existing_candidate_count=existing_candidate_count,
        incoming_count=incoming_count,
        drop_ratio=drop_ratio,
    )
