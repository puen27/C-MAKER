"""월간 모집단 적재 배치 진입점 (REQ-16, UC-17) — cron 매월 1일 01:00.

일간 07:30 SLA 파이프라인과 프로세스를 분리한다(4-project-principle.md §2). 실패해도 일간 배치는
이미 적재된 BUSINESS로 동작한다.

1) 소진공 상가(상권)정보: 지점별 반경 내 영업 중 업소 전수 (SBIZ, WGS84)
2) 지방행정 인허가 전수 파일: PERMIT_FULL_DATA_DIR의 *.csv (EPSG:5174 → WGS84 변환)

실행: python -m backend.batch.run_monthly [--as-of YYYY-MM-DD] [--skip-sbiz] [--skip-permit]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

from backend.batch import batch_repository as repo
from backend.batch.connectors import permit_connector, sbiz_connector
from backend.batch.connectors.http_client import FetchResult, SourceFetchError
from backend.batch.normalizers.permit_parser import parse_permit_row
from backend.batch.population.business_loader import AreaIndex, apply_permit_records, apply_sbiz_records
from backend.common.config import get_pipeline_config, get_settings, today_kst
from backend.common.db.advisory_lock import BATCH_MUTATION_LOCK_KEY, acquire_advisory_lock
from backend.common.db.pool import close_pool, get_connection
from backend.common.log_setup import log_fields, setup_logging
from backend.common.schemas.business import PermitRecord
from backend.common.snapshot_store import archive_source_file, save_snapshot

logger = logging.getLogger("monthly")


class MonthlyBatchSafetyError(RuntimeError):
    """수집 완전성 또는 원자 publish 조건을 만족하지 못한 월간 배치 오류."""


def _validate_sbiz_publish_options(options: dict[str, Any]) -> tuple[int, float]:
    min_records = options.get("min_population_records")
    if isinstance(min_records, bool) or not isinstance(min_records, int) or min_records < 1:
        raise MonthlyBatchSafetyError("SBIZ min_population_records는 1 이상의 정수여야 합니다")

    max_drop_ratio = options.get("max_population_drop_ratio")
    if isinstance(max_drop_ratio, bool) or not isinstance(max_drop_ratio, (int, float)):
        raise MonthlyBatchSafetyError("SBIZ max_population_drop_ratio는 0 이상 1 미만의 수여야 합니다")
    ratio = float(max_drop_ratio)
    if not 0 <= ratio < 1:
        raise MonthlyBatchSafetyError("SBIZ max_population_drop_ratio는 0 이상 1 미만이어야 합니다")
    return min_records, ratio


def _read_sbiz_manifest(result: FetchResult) -> list[dict[str, Any]]:
    payload = result.payload
    if not isinstance(payload, dict) or payload.get("complete") is not True:
        raise SourceFetchError("SBIZ 응답에 complete=true manifest가 없습니다")
    items = payload.get("items")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise SourceFetchError("SBIZ manifest items 형식이 올바르지 않습니다")
    try:
        unique_count = int(payload["unique_count"])
        total_count = int(payload["total_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SourceFetchError("SBIZ manifest count 형식이 올바르지 않습니다") from exc

    ids = [str(item.get("bizesId") or "").strip() for item in items]
    nonempty_ids = [store_id for store_id in ids if store_id]
    if (
        len(nonempty_ids) != len(set(nonempty_ids))
        or len(set(nonempty_ids)) != unique_count
        or unique_count != total_count
    ):
        raise SourceFetchError(
            f"SBIZ manifest 완전성 검증 실패: unique={len(set(nonempty_ids))}, "
            f"manifest_unique={unique_count}, total={total_count}"
        )
    return items


def _major_sbiz_values(item: dict[str, Any]) -> tuple[Any, ...]:
    def coordinate(key: str) -> float | str:
        value = item.get(key)
        try:
            return round(float(value), 7)
        except (TypeError, ValueError):
            return str(value or "").strip()

    text_keys = (
        "bizesNm",
        "brchNm",
        "indsLclsCd",
        "indsMclsCd",
        "indsSclsCd",
        "indsLclsNm",
        "indsMclsNm",
        "indsSclsNm",
        "rdnmAdr",
        "lnoAdr",
    )
    return tuple(str(item.get(key) or "").strip() for key in text_keys) + (
        coordinate("lat"),
        coordinate("lon"),
    )


def _merge_sbiz_items(branch_items: list[list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], int]:
    merged: dict[str, dict[str, Any]] = {}
    total_input = 0
    for items in branch_items:
        total_input += len(items)
        for item in items:
            store_id = str(item.get("bizesId") or "").strip()
            if not store_id:
                raise MonthlyBatchSafetyError("비어 있는 bizesId가 있어 SBIZ publish를 중단합니다")
            previous = merged.get(store_id)
            if previous is not None and _major_sbiz_values(previous) != _major_sbiz_values(item):
                raise MonthlyBatchSafetyError(f"중첩 지점의 SBIZ payload가 충돌합니다: bizesId={store_id}")
            merged.setdefault(store_id, item)
    return list(merged.values()), total_input


def load_sbiz(area: AreaIndex, as_of: date) -> dict[str, object]:
    settings = get_settings()
    source = get_pipeline_config().sources["SBIZ_STORE"]
    min_population_records, max_population_drop_ratio = _validate_sbiz_publish_options(
        source.options
    )
    if not settings.data_go_kr_service_key:
        log_fields(logger, logging.WARNING, "DATA_GO_KR_SERVICE_KEY 미설정 — 상가정보 적재를 건너뜁니다")
        return {"skipped": "NOT_CONFIGURED", "publish_complete": False}

    collected: list[list[dict[str, Any]]] = []
    failed_branches: list[str] = []
    snapshot_ids: list[int] = []
    for branch in area.branches:
        if not branch.has_coordinates:
            continue
        try:
            result = sbiz_connector.fetch_stores_in_radius(
                settings.data_go_kr_service_key,
                source.url,
                lat=branch.lat,  # type: ignore[arg-type]
                lng=branch.lng,  # type: ignore[arg-type]
                radius_m=int(branch.coverage_radius_km * 1000),
                page_size=int(source.options.get("page_size", 1000)),
            )
            items = _read_sbiz_manifest(result)
            # 지점별 성공 응답은 BUSINESS 가공 전에 각각 독립 commit한다(PRIN-08).
            with get_connection() as conn:
                snapshot_id = save_snapshot(
                    conn,
                    "SBIZ_STORE",
                    as_of,
                    result.payload,
                    {**result.request_params, "branch_code": branch.branch_code},
                )
            collected.append(items)
            snapshot_ids.append(snapshot_id)
            log_fields(
                logger,
                logging.INFO,
                "상가정보 원본 snapshot 저장",
                branch_code=branch.branch_code,
                snapshot_id=snapshot_id,
                unique_count=result.payload["unique_count"],
                total_count=result.payload["total_count"],
            )
        except Exception as exc:
            failed_branches.append(branch.branch_code)
            log_fields(
                logger,
                logging.ERROR,
                "상가정보 수집 또는 snapshot 저장 실패",
                branch_code=branch.branch_code,
                error_class=type(exc).__name__,
            )

    if failed_branches:
        raise MonthlyBatchSafetyError(
            f"SBIZ 지점 수집 실패로 전체 publish를 중단합니다: {', '.join(failed_branches)}"
        )

    merged_items, total_input = _merge_sbiz_items(collected)
    # 검증·upsert·전역 누락 폐업 판정을 하나의 transaction으로 묶는다.
    with get_connection() as conn:
        result = apply_sbiz_records(
            conn,
            merged_items,
            area,
            as_of,
            min_population_records=min_population_records,
            max_population_drop_ratio=max_population_drop_ratio,
        )

    summary: dict[str, object] = {
        "branches": len(collected),
        "total_input": total_input,
        "unique_count": result.unique_count,
        "upserted": result.upserted,
        "marked_closed": result.marked_closed,
        "existing_candidate_count": result.existing_candidate_count,
        "incoming_count": result.incoming_count,
        "drop_ratio": result.drop_ratio,
        "snapshot_ids": snapshot_ids,
        "publish_complete": True,
    }
    log_fields(logger, logging.INFO, "상가정보 전역 publish 완료", **summary)
    return summary


def _iter_permit_records(file_path: Path, counts: dict[str, int]) -> Iterator[PermitRecord]:
    for row in permit_connector.fetch_all_businesses(file_path):
        counts["rows"] += 1
        record = parse_permit_row(row)
        if record is None:
            counts["parse_skipped"] += 1
            continue
        counts["parsed_rows"] += 1
        yield record


def load_permit_files(area: AreaIndex, as_of: date) -> dict[str, object]:
    settings = get_settings()
    if not settings.permit_full_data_dir:
        log_fields(logger, logging.WARNING, "PERMIT_FULL_DATA_DIR 미설정 — 인허가 전수 적재를 건너뜁니다")
        return {"skipped": "NOT_CONFIGURED", "publish_complete": False}

    files = sorted(Path(settings.permit_full_data_dir).glob("*.csv"))
    if not files:
        raise MonthlyBatchSafetyError(
            f"PERMIT_FULL_DATA_DIR에 CSV 파일이 없습니다: {settings.permit_full_data_dir}"
        )

    archived: list[tuple[Path, str, int]] = []
    for file_path in files:
        # 모든 파일을 먼저 불변 archive하고 snapshot metadata를 파일별 독립 transaction으로 commit한다.
        archive_meta = archive_source_file("PERMIT_FULL", as_of, file_path)
        archived_value = archive_meta.get("archived_path")
        if not isinstance(archived_value, str) or not archived_value:
            raise MonthlyBatchSafetyError("PERMIT archive 경로가 누락되었습니다")
        archived_path = Path(archived_value)
        if not archived_path.is_file():
            raise MonthlyBatchSafetyError("PERMIT archive 파일을 확인할 수 없습니다")
        with get_connection() as conn:
            snapshot_id = save_snapshot(
                conn,
                "PERMIT_FULL",
                as_of,
                archive_meta,
                {"file": file_path.name},
            )
        archived.append((archived_path, file_path.name, snapshot_id))
        log_fields(
            logger,
            logging.INFO,
            "인허가 전수 원본 snapshot 저장",
            file=file_path.name,
            snapshot_id=snapshot_id,
        )

    summary: dict[str, object] = {
        "files": len(files),
        "rows": 0,
        "parsed_rows": 0,
        "parse_skipped": 0,
        "upserted": 0,
        "status_updated": 0,
        "skipped_out_of_area": 0,
        "skipped_invalid": 0,
        "new_openings": 0,
    }
    file_logs: list[dict[str, object]] = []
    # 한 파일이라도 parse/DB 실패하면 이 connection context가 전체 PERMIT 변경을 rollback한다.
    with get_connection() as conn:
        for archived_path, original_name, snapshot_id in archived:
            started = time.monotonic()
            counts = {"rows": 0, "parsed_rows": 0, "parse_skipped": 0}
            result = apply_permit_records(conn, _iter_permit_records(archived_path, counts), area, as_of)
            result_values = result.as_dict()
            for key, value in counts.items():
                summary[key] = int(summary[key]) + value
            for key, value in result_values.items():
                summary[key] = int(summary[key]) + value
            file_logs.append(
                {
                    "file": original_name,
                    "snapshot_id": snapshot_id,
                    "elapsed_s": round(time.monotonic() - started, 1),
                    **counts,
                    **result_values,
                }
            )

    summary["publish_complete"] = True
    for fields in file_logs:
        log_fields(logger, logging.INFO, "인허가 전수 파일 publish 완료", **fields)
    log_fields(logger, logging.INFO, "인허가 전수 전체 publish 완료", **summary)
    return summary


def run(as_of: date, *, skip_sbiz: bool = False, skip_permit: bool = False) -> dict[str, object]:
    setup_logging("monthly")
    with get_connection() as conn:
        branches = repo.load_current_branches(conn)
    missing = [b.branch_code for b in branches if not b.has_coordinates]
    if missing:
        log_fields(logger, logging.WARNING, "좌표가 없는 지점은 적재 범위에서 제외됩니다(지오코딩 대기)", branches=missing)
    area = AreaIndex([b for b in branches if b.has_coordinates])
    if not area.branches:
        raise MonthlyBatchSafetyError("좌표 보유 지점이 0건이므로 외부 소스 수집을 시작하지 않습니다")
    # 모집단 적재 기준월(REQ-16) — 모든 행에 기록된다(UC-17 인수 기준 5)
    population_as_of = as_of.replace(day=1)

    summary: dict[str, object] = {"population_as_of": population_as_of.isoformat()}
    if not skip_sbiz:
        summary["sbiz"] = load_sbiz(area, population_as_of)
    if not skip_permit:
        summary["permit"] = load_permit_files(area, population_as_of)
    log_fields(logger, logging.INFO, "월간 모집단 적재 완료", **summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C-MAKER 월간 모집단 적재")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    parser.add_argument("--skip-sbiz", action="store_true")
    parser.add_argument("--skip-permit", action="store_true")
    args = parser.parse_args(argv)
    try:
        setup_logging("monthly")
        with acquire_advisory_lock(BATCH_MUTATION_LOCK_KEY) as acquired:
            if not acquired:
                log_fields(
                    logger,
                    logging.WARNING,
                    "다른 배치가 데이터 변경 잠금을 사용 중이어서 월간 모집단 적재를 실행하지 않습니다",
                )
                return 1
            try:
                run(args.as_of or today_kst(), skip_sbiz=args.skip_sbiz, skip_permit=args.skip_permit)
            except Exception as exc:
                log_fields(
                    logger,
                    logging.ERROR,
                    "월간 모집단 적재 실패",
                    error_class=type(exc).__name__,
                )
                return 1
            return 0
    finally:
        close_pool()


if __name__ == "__main__":
    sys.exit(main())
