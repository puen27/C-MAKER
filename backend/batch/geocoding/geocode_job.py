"""지점 좌표 지오코딩 잡 (RULE-BRANCH-03) — cron 10분 주기, run_daily.py와 무관한 별도 진입점.

대상: lat/lng가 NULL이거나 좌표를 산출한 주소(geocoded_address)가 현재 주소와 다른 지점.
결정 사항(docs/db-schema-decisions-review.md §5)에 따라 잡 내부 재시도·알림·모니터링은 두지 않는다.
좌표 UPDATE는 BRANCH 트리거가 이력·effective_from을 처리하므로 새 좌표는 다음 날 07:30부터 반영된다.

실행: python -m backend.batch.geocoding.geocode_job
"""

from __future__ import annotations

import logging
import sys

from backend.batch import batch_repository as repo
from backend.batch.connectors.http_client import SourceFetchError
from backend.batch.connectors.vworld_connector import geocode_address
from backend.common.config import get_pipeline_config, get_settings
from backend.common.db.advisory_lock import GEOCODE_LOCK_KEY, acquire_advisory_lock
from backend.common.db.pool import close_pool, get_connection
from backend.common.geo import to_wgs84
from backend.common.log_setup import log_fields, setup_logging


def run() -> dict[str, int]:
    logger = setup_logging("geocode")
    settings = get_settings()
    source = get_pipeline_config().sources["VWORLD_GEOCODER"]
    stats = {"targets": 0, "updated": 0, "not_found": 0, "failed": 0}

    if not settings.vworld_api_key:
        log_fields(logger, logging.WARNING, "VWORLD_API_KEY 미설정 — 지오코딩을 건너뜁니다")
        return stats

    with get_connection() as conn:
        targets = repo.load_branches_to_geocode(conn)
    stats["targets"] = len(targets)

    for branch in targets:
        try:
            point = geocode_address(settings.vworld_api_key, source.url, branch["address"])
        except SourceFetchError as exc:
            stats["failed"] += 1
            log_fields(logger, logging.WARNING, "지오코딩 실패", branch_code=branch["branch_code"], error=str(exc))
            continue
        if point is None or to_wgs84(point[1], point[0], "EPSG:4326") is None:
            stats["not_found"] += 1
            log_fields(logger, logging.WARNING, "주소를 찾지 못함", branch_code=branch["branch_code"])
            continue
        with get_connection() as conn:
            if repo.update_branch_coordinates(conn, branch["id"], branch["address"], point[0], point[1]):
                stats["updated"] += 1

    log_fields(logger, logging.INFO, "지오코딩 완료", **stats)
    return stats


def main() -> int:
    try:
        logger = setup_logging("geocode")
        with acquire_advisory_lock(GEOCODE_LOCK_KEY) as acquired:
            if not acquired:
                log_fields(logger, logging.WARNING, "중복 cron 실행으로 판단해 지오코딩을 건너뜁니다")
                return 0
            run()
            return 0
    finally:
        close_pool()


if __name__ == "__main__":
    sys.exit(main())
