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
from datetime import date
from pathlib import Path

from backend.batch import batch_repository as repo
from backend.batch.connectors import permit_connector, sbiz_connector
from backend.batch.connectors.http_client import SourceFetchError
from backend.batch.normalizers.permit_parser import parse_permit_row
from backend.batch.population.business_loader import AreaIndex, apply_permit_records, load_sbiz_for_branch
from backend.common.config import get_pipeline_config, get_settings, today_kst
from backend.common.db.pool import close_pool, get_connection
from backend.common.log_setup import log_fields, setup_logging
from backend.common.snapshot_store import archive_source_file, save_snapshot

logger = logging.getLogger("monthly")


def load_sbiz(area: AreaIndex, as_of: date) -> dict[str, object]:
    settings = get_settings()
    source = get_pipeline_config().sources["SBIZ_STORE"]
    summary: dict[str, object] = {"branches": 0, "failed": []}
    if not settings.data_go_kr_service_key:
        log_fields(logger, logging.WARNING, "DATA_GO_KR_SERVICE_KEY 미설정 — 상가정보 적재를 건너뜁니다")
        summary["skipped"] = "NOT_CONFIGURED"
        return summary

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
        except SourceFetchError as exc:
            summary["failed"].append(branch.branch_code)  # type: ignore[union-attr]
            log_fields(logger, logging.ERROR, "상가정보 수집 실패", branch_code=branch.branch_code, error=str(exc))
            continue

        items = result.payload["items"]
        complete = len(items) >= int(result.payload["total_count"])
        with get_connection() as conn:
            # 원본을 가공 전에 먼저 보존한다(CLAUDE.md §1)
            snapshot_id = save_snapshot(
                conn, "SBIZ_STORE", as_of, result.payload, {**result.request_params, "branch_code": branch.branch_code}
            )
            stats = load_sbiz_for_branch(conn, branch, items, as_of, complete=complete)
        summary["branches"] = int(summary["branches"]) + 1  # type: ignore[call-overload]
        log_fields(logger, logging.INFO, "상가정보 적재", branch_code=branch.branch_code,
                   snapshot_id=snapshot_id, complete=complete, **stats)
    return summary


def load_permit_files(area: AreaIndex, as_of: date) -> dict[str, object]:
    settings = get_settings()
    summary: dict[str, object] = {"files": 0}
    if not settings.permit_full_data_dir:
        log_fields(logger, logging.WARNING, "PERMIT_FULL_DATA_DIR 미설정 — 인허가 전수 적재를 건너뜁니다")
        summary["skipped"] = "NOT_CONFIGURED"
        return summary

    files = sorted(Path(settings.permit_full_data_dir).glob("*.csv"))
    for file_path in files:
        started = time.monotonic()
        # 수백 MB 원본은 파일로 날짜 파티션 보관하고 스냅샷에는 메타데이터만 남긴다(재현성, OPS-05).
        archive_meta = archive_source_file("PERMIT_FULL", as_of, file_path)
        with get_connection() as conn:
            snapshot_id = save_snapshot(conn, "PERMIT_FULL", as_of, archive_meta, {"file": file_path.name})
            permits = (
                record
                for record in (parse_permit_row(row) for row in permit_connector.fetch_all_businesses(file_path))
                if record is not None
            )
            result = apply_permit_records(conn, permits, area, as_of)
        summary["files"] = int(summary["files"]) + 1  # type: ignore[call-overload]
        log_fields(logger, logging.INFO, "인허가 전수 적재", file=file_path.name, snapshot_id=snapshot_id,
                   elapsed_s=round(time.monotonic() - started, 1), **result.as_dict())
    return summary


def run(as_of: date, *, skip_sbiz: bool = False, skip_permit: bool = False) -> dict[str, object]:
    setup_logging("monthly")
    with get_connection() as conn:
        branches = repo.load_current_branches(conn)
    missing = [b.branch_code for b in branches if not b.has_coordinates]
    if missing:
        log_fields(logger, logging.WARNING, "좌표가 없는 지점은 적재 범위에서 제외됩니다(지오코딩 대기)", branches=missing)
    area = AreaIndex([b for b in branches if b.has_coordinates])
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
        run(args.as_of or today_kst(), skip_sbiz=args.skip_sbiz, skip_permit=args.skip_permit)
        return 0
    finally:
        close_pool()


if __name__ == "__main__":
    sys.exit(main())
