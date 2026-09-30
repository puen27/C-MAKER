"""배치 수동 재실행(REQ-17, UC-18)과 데이터 신선도(RULE-SENSE-04 지연 배너).

RULE-SENSE-06 / VAL-12 검증 순서
1. 역할: 지점장·본부(마케팅)만 (라우터 의존성 + 여기서 재확인)
2. 이미 RUNNING인 실행이 있으면 새로 만들지 않고 기존 실행을 돌려준다(중복 실행 방지)
3. 같은 계정의 직전 수동 요청 후 쿨다운(BATCH_COOLDOWN_MINUTES, 기본 30분) 이내면 거부
4. BATCH_RUN(MANUAL, RUNNING) 생성 → 커밋 → run_daily.py를 별도 프로세스로 기동하고 즉시 응답

배치 오케스트레이션 프레임워크는 쓰지 않는다(PRIN-02). 프런트엔드는 /api/batch/status를 폴링한다.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

import psycopg

from backend.api.middlewares.error_middleware import ForbiddenError, TooManyRequestsError
from backend.api.repositories import audit_repository, batch_run_repository, recommendation_repository
from backend.common.config import KST, REPO_ROOT, get_pipeline_config, get_settings, today_kst
from backend.common.db.advisory_lock import (
    BATCH_MUTATION_LOCK_KEY,
    acquire_advisory_lock_connection,
)
from backend.common.db.pool import get_connection
from backend.common.schemas.auth import CurrentUser
from backend.common.schemas.batch_run import (
    BatchRunView,
    BatchStatusResponse,
    BatchTriggerResponse,
    DataFreshnessResponse,
    SourceFreshness,
)

logger = logging.getLogger("api.batch")

TRIGGER_ROLES = {"BRANCH_MANAGER", "HQ_MARKETING"}
DEFAULT_EXPECTED_DURATION = timedelta(minutes=15)
SLA_TIME = time(7, 30)


def _to_view(conn: psycopg.Connection, row: dict[str, Any] | None) -> BatchRunView | None:
    if row is None:
        return None
    expected = None
    if row["status"] == "RUNNING":
        average = batch_run_repository.average_duration_seconds(conn)
        duration = timedelta(seconds=average) if average else DEFAULT_EXPECTED_DURATION
        expected = (row["started_at"] or row["requested_at"]) + duration
    return BatchRunView(
        id=row["id"], run_type=row["run_type"], status=row["status"], target_date=row["target_date"],
        triggered_by_name=row["triggered_by_name"], requested_at=row["requested_at"],
        started_at=row["started_at"], completed_at=row["completed_at"], expected_completion_at=expected,
        failure_reason=row["failure_reason"],
    )


def cooldown_remaining_seconds(conn: psycopg.Connection, user_id: int, now: datetime | None = None) -> int:
    last = batch_run_repository.last_manual_request(conn, user_id)
    if last is None:
        return 0
    now = now or datetime.now(KST)
    available_at = last["requested_at"] + timedelta(minutes=get_settings().batch_cooldown_minutes)
    return max(0, int((available_at - now).total_seconds()))


def _fail_stale_if_lock_available(_conn: psycopg.Connection) -> tuple[bool, int]:
    """worker 부재를 확인한 잠금 세션에서 stale 정리하고 잠금 획득 여부와 건수를 반환한다."""
    with acquire_advisory_lock_connection(BATCH_MUTATION_LOCK_KEY) as (acquired, lock_conn):
        if not acquired:
            return False, 0
        stale_count = batch_run_repository.fail_stale(lock_conn, get_settings().batch_stale_minutes)
        return True, stale_count


def get_status(conn: psycopg.Connection, user: CurrentUser) -> BatchStatusResponse:
    _fail_stale_if_lock_available(conn)
    return BatchStatusResponse(
        latest_run=_to_view(conn, batch_run_repository.latest(conn)),
        cooldown_remaining_seconds=cooldown_remaining_seconds(conn, user.id),
        cooldown_minutes=get_settings().batch_cooldown_minutes,
    )


def _mark_orphaned_manual_run_failed(run_id: int, failure_reason: str) -> None:
    """새 커넥션에서 RUNNING 수동 실행만 실패 처리하고 완료 감사를 같은 트랜잭션에 남긴다."""
    with get_connection() as conn:
        row = batch_run_repository.get(conn, run_id)
        if row is None or row["run_type"] != "MANUAL" or row["status"] != "RUNNING":
            return
        if batch_run_repository.mark_failed(conn, run_id, failure_reason):
            audit_repository.insert(
                conn,
                actor_user_id=row["triggered_by"],
                action="BATCH_RUN_COMPLETED",
                entity_type="batch_run",
                entity_id=str(run_id),
                after_value={
                    "status": "FAILED",
                    "failure_reason": failure_reason,
                    "run_type": "MANUAL",
                },
            )


def _watch_daily_batch(run_id: int, process: Any) -> None:
    exit_code = process.wait()
    failure_reason = f"배치 프로세스가 완료 상태를 기록하지 않고 종료됨(exit_code={exit_code})"
    try:
        _mark_orphaned_manual_run_failed(run_id, failure_reason)
    except Exception:  # noqa: BLE001 — daemon watcher의 DB 실패는 API 프로세스를 중단하지 않고 기록한다
        logger.exception("종료된 배치 프로세스 상태 정리 실패", extra={"run_id": run_id})


def _spawn_daily_batch(run_id: int) -> None:
    settings = get_settings()
    command = [sys.executable, "-m", "backend.batch.run_daily", "--run-id", str(run_id)]
    if settings.log_dir:
        stdout: Any = subprocess.DEVNULL  # 배치가 LOG_DIR/daily.log에 직접 기록한다
    else:
        log_path = Path(REPO_ROOT) / "data" / "logs" / "daily-manual.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stdout = log_path.open("ab")
    kwargs: dict[str, Any] = {"cwd": str(REPO_ROOT), "stdin": subprocess.DEVNULL, "stdout": stdout,
                              "stderr": subprocess.STDOUT, "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    process = subprocess.Popen(command, **kwargs)  # noqa: S603 — 고정 인자, 사용자 입력 없음
    # 종료된 자식 프로세스를 회수하고, worker가 terminal 상태를 기록하지 못한 경우 안전하게 실패 처리한다.
    threading.Thread(target=_watch_daily_batch, args=(run_id, process), daemon=True).start()


def trigger(conn: psycopg.Connection, user: CurrentUser) -> BatchTriggerResponse:
    if user.role not in TRIGGER_ROLES:
        raise ForbiddenError("배치 수동 재실행 권한이 없습니다.")
    lock_acquired, _stale_count = _fail_stale_if_lock_available(conn)

    running = batch_run_repository.running(conn)
    if running is not None:
        view = _to_view(conn, running)
        assert view is not None
        return BatchTriggerResponse(run=view, already_running=True)
    if not lock_acquired:
        raise TooManyRequestsError(
            "다른 배치가 시작 중이거나 실행 중입니다. 잠시 후 다시 시도해주세요.",
            code="BATCH_RUNNING",
        )

    remaining = cooldown_remaining_seconds(conn, user.id)
    if remaining > 0:
        minutes = max(1, -(-remaining // 60))
        raise TooManyRequestsError(f"{minutes}분 후 다시 시도할 수 있습니다.", code="BATCH_COOLDOWN")

    run_id = batch_run_repository.create_manual_run(conn, user.id, today_kst())
    if run_id is None:  # 동시 요청 경쟁 — 다른 요청이 먼저 RUNNING을 만들었다
        view = _to_view(conn, batch_run_repository.running(conn))
        assert view is not None
        return BatchTriggerResponse(run=view, already_running=True)

    audit_repository.insert(conn, actor_user_id=user.id, action="BATCH_RUN_REQUESTED", entity_type="batch_run",
                            entity_id=str(run_id), after_value={"run_type": "MANUAL"})
    conn.commit()  # 배치 프로세스가 RUNNING 행을 볼 수 있도록 기동 전에 커밋한다
    try:
        _spawn_daily_batch(run_id)
    except OSError as exc:
        logger.exception("배치 프로세스 기동 실패")
        failure_reason = f"배치 프로세스 기동 실패: {type(exc).__name__}"
        if batch_run_repository.mark_failed(conn, run_id, failure_reason):
            audit_repository.insert(
                conn,
                actor_user_id=user.id,
                action="BATCH_RUN_COMPLETED",
                entity_type="batch_run",
                entity_id=str(run_id),
                after_value={
                    "status": "FAILED",
                    "failure_reason": failure_reason,
                    "run_type": "MANUAL",
                },
            )
    view = _to_view(conn, batch_run_repository.get(conn, run_id))
    assert view is not None
    return BatchTriggerResponse(run=view, already_running=False)


def get_data_freshness(conn: psycopg.Connection, user: CurrentUser) -> DataFreshnessResponse:
    """지연 배너 판정: 배치 실패, 소스 지연·수집 불가, 명부 미생성, SLA 미완료."""
    config = get_pipeline_config()
    today = today_kst()
    finished = batch_run_repository.latest_finished_for_date(conn, today)
    running = batch_run_repository.running(conn)

    sources: list[SourceFreshness] = []
    for item in (finished or {}).get("source_status") or []:
        if item.get("status") == "SKIPPED":
            continue
        sources.append(
            SourceFreshness(
                source_name=item["source_name"],
                display_name=config.source_display_name(item["source_name"]),
                status=item["status"],
                latest_as_of_date=item.get("as_of_date"),
                expected_as_of_date=item["expected_as_of"],
                delay_days=int(item.get("delay_days") or 0),
                is_fallback=bool(item.get("is_fallback")),
            )
        )
    max_delay = max((source.delay_days for source in sources), default=0)
    list_ready = recommendation_repository.has_list(conn, today, user.branch_id)

    unavailable_names = [source.display_name for source in sources if source.status == "UNAVAILABLE"]
    degraded_names = [source.display_name for source in sources if source.status == "DEGRADED"]
    has_fallback = any(source.status == "FALLBACK" or source.is_fallback for source in sources)

    def format_source_names(names: list[str]) -> str:
        displayed_names = ", ".join(names[:3])
        remaining_count = len(names) - 3
        suffix = f" 외 {remaining_count}개" if remaining_count > 0 else ""
        return f"{displayed_names}{suffix}"

    message: str | None = None
    if finished is not None and finished["status"] == "FAILED":
        message = "오늘 일간 배치가 실패했습니다. 일부 데이터가 최신이 아닐 수 있습니다."
    elif unavailable_names:
        message = f"일부 데이터를 수집하지 못했습니다: {format_source_names(unavailable_names)}."
    elif degraded_names:
        message = f"일부 데이터 정규화가 완료되지 않았습니다: {format_source_names(degraded_names)}."
    elif has_fallback or max_delay > 0:
        message = (f"일부 신호가 지연되었습니다(기준일 {max_delay}일 전)." if max_delay > 0
                   else "일부 신호가 지연되었습니다.")
    elif finished is not None and finished["status"] == "SUCCESS" and not list_ready:
        message = "오늘 추천 명부가 생성되지 않았습니다."
    elif finished is None and datetime.now(KST).time() >= SLA_TIME:
        message = ("오늘 일간 배치가 실행 중입니다." if running is not None
                   else "오늘 일간 배치가 아직 완료되지 않았습니다.")

    return DataFreshnessResponse(
        reference_date=today,
        delayed=message is not None,
        max_delay_days=max_delay,
        todays_list_ready=list_ready,
        latest_run_status=(running or finished or {}).get("status"),
        message=message,
        sources=sources,
    )
