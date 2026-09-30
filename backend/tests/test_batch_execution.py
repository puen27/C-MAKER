"""P0 배치 실행 제어: advisory lock, stale 정리, watcher, 상태 fencing 단위 테스트."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from backend.api.repositories import batch_run_repository
from backend.api.services import batch_service
from backend.batch import batch_repository, run_daily, run_monthly
from backend.batch.geocoding import geocode_job
from backend.common.config import KST
from backend.common.db import advisory_lock
from backend.common.db import pool as db_pool
from backend.common.schemas.auth import CurrentUser


class FakeCursor:
    def __init__(self, row: dict[str, Any] | None = None, rowcount: int = 0) -> None:
        self.row = row
        self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class FakeLockConnection:
    def __init__(self, acquired: bool, *, fail_try: bool = False) -> None:
        self.acquired = acquired
        self.fail_try = fail_try
        self.closed = False
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.closed = True

    def execute(self, sql: str, params: tuple[Any, ...]) -> FakeCursor:
        self.statements.append((sql, params))
        if "pg_try_advisory_lock" in sql:
            if self.fail_try:
                raise RuntimeError("database unavailable")
            return FakeCursor({"acquired": self.acquired})
        if "pg_advisory_unlock" in sql:
            return FakeCursor({"released": self.acquired})
        return FakeCursor()


def _patch_direct_connection(monkeypatch, conn: FakeLockConnection) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(advisory_lock, "build_conninfo", lambda: "postgresql://direct-lock")

    def connect(conninfo: str, **kwargs: Any) -> FakeLockConnection:
        calls.append({"conninfo": conninfo, **kwargs})
        return conn

    monkeypatch.setattr(advisory_lock.psycopg, "connect", connect)
    return calls


@pytest.mark.parametrize("acquired", [True, False])
def test_advisory_lock_uses_direct_connection_and_unlocks_same_session(monkeypatch, acquired):
    conn = FakeLockConnection(acquired)
    calls = _patch_direct_connection(monkeypatch, conn)

    with advisory_lock.acquire_advisory_lock(advisory_lock.BATCH_MUTATION_LOCK_KEY) as result:
        assert result is acquired

    assert calls == [
        {
            "conninfo": "postgresql://direct-lock",
            "autocommit": True,
            "row_factory": advisory_lock.dict_row,
        }
    ]
    assert "pg_try_advisory_lock" in conn.statements[0][0]
    unlocks = [statement for statement in conn.statements if "pg_advisory_unlock" in statement[0]]
    assert len(unlocks) == int(acquired)
    if unlocks:
        assert unlocks[0][1] == (advisory_lock.BATCH_MUTATION_LOCK_KEY,)
    assert conn.closed is True


def test_advisory_lock_releases_same_connection_when_body_raises(monkeypatch):
    conn = FakeLockConnection(True)
    _patch_direct_connection(monkeypatch, conn)

    with pytest.raises(ValueError, match="pipeline failed"):
        with advisory_lock.acquire_advisory_lock(advisory_lock.BATCH_MUTATION_LOCK_KEY) as acquired:
            assert acquired is True
            raise ValueError("pipeline failed")

    assert sum("pg_advisory_unlock" in sql for sql, _ in conn.statements) == 1


def test_advisory_lock_database_error_is_not_fail_open(monkeypatch):
    conn = FakeLockConnection(False, fail_try=True)
    _patch_direct_connection(monkeypatch, conn)

    with pytest.raises(RuntimeError, match="database unavailable"):
        with advisory_lock.acquire_advisory_lock(advisory_lock.BATCH_MUTATION_LOCK_KEY):
            pytest.fail("잠금 DB 오류에서 본문을 실행하면 안 됩니다")

    assert not any("pg_advisory_unlock" in sql for sql, _ in conn.statements)


def test_advisory_lock_does_not_consume_single_connection_pool(monkeypatch):
    lock_conn = FakeLockConnection(True)
    _patch_direct_connection(monkeypatch, lock_conn)

    class SingleConnectionPool:
        def __init__(self) -> None:
            self.in_use = False
            self.entries = 0

        @contextmanager
        def connection(self):
            assert self.in_use is False
            self.in_use = True
            self.entries += 1
            try:
                yield object()
            finally:
                self.in_use = False

    pool = SingleConnectionPool()
    monkeypatch.setattr(db_pool, "open_pool", lambda: pool)

    with advisory_lock.acquire_advisory_lock(advisory_lock.BATCH_MUTATION_LOCK_KEY) as acquired:
        assert acquired is True
        with db_pool.get_connection():
            pass

    assert pool.entries == 1


@pytest.mark.parametrize(("acquired", "expected_calls"), [(True, 1), (False, 0)])
def test_api_stale_cleanup_commits_on_lock_connection_before_unlock(monkeypatch, acquired, expected_calls):
    lock_keys: list[int] = []
    stale_calls: list[tuple[object, int]] = []
    order: list[str] = []
    lock_conn = object()

    @contextmanager
    def fake_acquire(lock_key: int):
        lock_keys.append(lock_key)
        order.append("lock")
        try:
            yield acquired, lock_conn
        finally:
            order.append("unlock")

    monkeypatch.setattr(batch_service, "acquire_advisory_lock_connection", fake_acquire)
    monkeypatch.setattr(batch_service, "get_settings", lambda: SimpleNamespace(batch_stale_minutes=180))

    def fail_stale(conn: object, minutes: int) -> int:
        order.append("stale")
        stale_calls.append((conn, minutes))
        return 2

    monkeypatch.setattr(batch_service.batch_run_repository, "fail_stale", fail_stale)
    request_conn = object()

    result = batch_service._fail_stale_if_lock_available(request_conn)  # type: ignore[arg-type]

    assert lock_keys == [advisory_lock.BATCH_MUTATION_LOCK_KEY]
    assert stale_calls == ([(lock_conn, 180)] if acquired else [])
    assert order == (["lock", "stale", "unlock"] if acquired else ["lock", "unlock"])
    assert len(stale_calls) == expected_calls
    assert result == ((True, 2) if acquired else (False, 0))


def _batch_run_row(
    *,
    run_id: int = 101,
    run_type: str = "SCHEDULED",
    status: str = "RUNNING",
) -> dict[str, Any]:
    requested_at = datetime(2026, 10, 1, 7, 0, tzinfo=KST)
    return {
        "id": run_id,
        "run_type": run_type,
        "status": status,
        "target_date": date(2026, 10, 1),
        "requested_at": requested_at,
        "started_at": requested_at,
        "completed_at": None,
        "failure_reason": None,
        "triggered_by": None if run_type == "SCHEDULED" else 31,
        "triggered_by_name": None if run_type == "SCHEDULED" else "테스트 관리자",
        "source_status": [],
    }


def test_get_status_keeps_response_contract_when_stale_lock_is_busy(monkeypatch):
    row = _batch_run_row(status="SUCCESS")
    cleanup_calls: list[object] = []
    conn = object()
    monkeypatch.setattr(
        batch_service,
        "_fail_stale_if_lock_available",
        lambda actual_conn: cleanup_calls.append(actual_conn) or (False, 0),
    )
    monkeypatch.setattr(batch_service.batch_run_repository, "latest", lambda actual_conn: row)
    monkeypatch.setattr(batch_service, "cooldown_remaining_seconds", lambda actual_conn, user_id: 17)
    monkeypatch.setattr(batch_service, "get_settings", lambda: SimpleNamespace(batch_cooldown_minutes=30))

    response = batch_service.get_status(
        conn,  # type: ignore[arg-type]
        CurrentUser(id=31, role="HQ_MARKETING", branch_id=None),
    )

    assert cleanup_calls == [conn]
    assert response.latest_run is not None
    assert response.latest_run.id == row["id"]
    assert response.cooldown_remaining_seconds == 17
    assert response.cooldown_minutes == 30


def test_trigger_lock_busy_without_running_row_raises_batch_running(monkeypatch):
    conn = object()
    monkeypatch.setattr(batch_service, "_fail_stale_if_lock_available", lambda actual_conn: (False, 0))
    monkeypatch.setattr(batch_service.batch_run_repository, "running", lambda actual_conn: None)
    monkeypatch.setattr(
        batch_service,
        "cooldown_remaining_seconds",
        lambda *args: pytest.fail("lock busy이면 쿨다운을 확인하면 안 됩니다"),
    )
    monkeypatch.setattr(
        batch_service.batch_run_repository,
        "create_manual_run",
        lambda *args: pytest.fail("lock busy이면 MANUAL 행을 만들면 안 됩니다"),
    )
    monkeypatch.setattr(
        batch_service,
        "_spawn_daily_batch",
        lambda *args: pytest.fail("lock busy이면 worker를 기동하면 안 됩니다"),
    )

    with pytest.raises(batch_service.TooManyRequestsError) as exc_info:
        batch_service.trigger(  # type: ignore[arg-type]
            conn,
            CurrentUser(id=31, role="HQ_MARKETING", branch_id=None),
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "BATCH_RUNNING"
    assert "다른 배치가 시작 중이거나 실행 중" in exc_info.value.message


def test_trigger_lock_busy_with_running_row_returns_existing(monkeypatch):
    row = _batch_run_row()
    monkeypatch.setattr(batch_service, "_fail_stale_if_lock_available", lambda actual_conn: (False, 0))
    monkeypatch.setattr(batch_service.batch_run_repository, "running", lambda actual_conn: row)
    monkeypatch.setattr(batch_service.batch_run_repository, "average_duration_seconds", lambda actual_conn: None)
    monkeypatch.setattr(
        batch_service.batch_run_repository,
        "create_manual_run",
        lambda *args: pytest.fail("기존 RUNNING 행이 있으면 MANUAL 행을 만들면 안 됩니다"),
    )
    monkeypatch.setattr(
        batch_service,
        "_spawn_daily_batch",
        lambda *args: pytest.fail("기존 RUNNING 행이 있으면 worker를 기동하면 안 됩니다"),
    )

    response = batch_service.trigger(  # type: ignore[arg-type]
        object(),
        CurrentUser(id=31, role="HQ_MARKETING", branch_id=None),
    )

    assert response.already_running is True
    assert response.run.id == row["id"]
    assert response.run.run_type == "SCHEDULED"


def test_trigger_lock_acquired_continues_stale_cooldown_create_and_spawn(monkeypatch):
    row = _batch_run_row(run_type="MANUAL")
    order: list[str] = []
    audits: list[dict[str, Any]] = []

    class TriggerConnection:
        def commit(self) -> None:
            order.append("commit")

    conn = TriggerConnection()
    monkeypatch.setattr(
        batch_service,
        "_fail_stale_if_lock_available",
        lambda actual_conn: order.append("stale") or (True, 2),
    )
    monkeypatch.setattr(
        batch_service.batch_run_repository,
        "running",
        lambda actual_conn: order.append("running") or None,
    )
    monkeypatch.setattr(
        batch_service,
        "cooldown_remaining_seconds",
        lambda actual_conn, user_id: order.append("cooldown") or 0,
    )
    monkeypatch.setattr(batch_service, "today_kst", lambda: date(2026, 10, 1))
    monkeypatch.setattr(
        batch_service.batch_run_repository,
        "create_manual_run",
        lambda actual_conn, user_id, target_date: order.append("create") or row["id"],
    )
    monkeypatch.setattr(
        batch_service.audit_repository,
        "insert",
        lambda actual_conn, **kwargs: (order.append("audit"), audits.append(kwargs)),
    )
    monkeypatch.setattr(
        batch_service,
        "_spawn_daily_batch",
        lambda run_id: order.append(f"spawn:{run_id}"),
    )
    monkeypatch.setattr(batch_service.batch_run_repository, "get", lambda actual_conn, run_id: row)
    monkeypatch.setattr(batch_service.batch_run_repository, "average_duration_seconds", lambda actual_conn: None)

    response = batch_service.trigger(  # type: ignore[arg-type]
        conn,
        CurrentUser(id=31, role="HQ_MARKETING", branch_id=None),
    )

    assert response.already_running is False
    assert response.run.id == row["id"]
    assert order == ["stale", "running", "cooldown", "create", "audit", "commit", "spawn:101"]
    assert audits[0]["action"] == "BATCH_RUN_REQUESTED"


def test_scheduled_start_interleaving_does_not_create_or_spawn_manual(monkeypatch):
    class FakeEvent:
        def __init__(self) -> None:
            self._set = False

        def set(self) -> None:
            self._set = True

        def is_set(self) -> bool:
            return self._set

    scheduled_lock_acquired = FakeEvent()
    scheduled_row_created = FakeEvent()
    scheduled_lock_acquired.set()
    state: dict[str, dict[str, Any] | None] = {"running": None}
    order = ["scheduled_lock_acquired"]
    manual_creates: list[int] = []
    manual_spawns: list[int] = []
    pipeline_runs: list[str] = []

    def fail_stale_during_scheduled_start(actual_conn: object) -> tuple[bool, int]:
        assert scheduled_lock_acquired.is_set() is True
        assert scheduled_row_created.is_set() is False
        order.append("api_lock_miss")
        return False, 0

    def get_running(actual_conn: object) -> dict[str, Any] | None:
        order.append("api_running_query")
        return state["running"]

    monkeypatch.setattr(batch_service, "_fail_stale_if_lock_available", fail_stale_during_scheduled_start)
    monkeypatch.setattr(batch_service.batch_run_repository, "running", get_running)
    monkeypatch.setattr(
        batch_service.batch_run_repository,
        "create_manual_run",
        lambda *args: manual_creates.append(201) or 201,
    )
    monkeypatch.setattr(batch_service, "_spawn_daily_batch", lambda run_id: manual_spawns.append(run_id))

    with pytest.raises(batch_service.TooManyRequestsError) as exc_info:
        batch_service.trigger(  # type: ignore[arg-type]
            object(),
            CurrentUser(id=31, role="HQ_MARKETING", branch_id=None),
        )

    # 예약 worker가 임계구역을 이어가 RUNNING 소유권을 얻고 파이프라인을 정확히 한 번 수행한다.
    if state["running"] is None:
        state["running"] = _batch_run_row()
        scheduled_row_created.set()
        order.append("scheduled_row_created")
        pipeline_runs.append("scheduled")

    assert exc_info.value.code == "BATCH_RUNNING"
    assert manual_creates == []
    assert manual_spawns == []
    assert pipeline_runs == ["scheduled"]
    assert order == [
        "scheduled_lock_acquired",
        "api_lock_miss",
        "api_running_query",
        "scheduled_row_created",
    ]


class FakeProcess:
    def __init__(self, exit_code: int) -> None:
        self.exit_code = exit_code
        self.waited = False

    def wait(self) -> int:
        self.waited = True
        return self.exit_code


def test_watcher_fails_running_manual_run_and_inserts_completion_audit(monkeypatch):
    conn = object()
    process = FakeProcess(9)
    failed: list[tuple[int, str]] = []
    audits: list[dict[str, Any]] = []

    @contextmanager
    def fake_get_connection():
        yield conn

    monkeypatch.setattr(batch_service, "get_connection", fake_get_connection)
    monkeypatch.setattr(
        batch_service.batch_run_repository,
        "get",
        lambda actual_conn, run_id: {
            "id": run_id,
            "run_type": "MANUAL",
            "status": "RUNNING",
            "triggered_by": 17,
        },
    )
    monkeypatch.setattr(
        batch_service.batch_run_repository,
        "mark_failed",
        lambda actual_conn, run_id, reason: failed.append((run_id, reason)) or True,
    )
    monkeypatch.setattr(
        batch_service.audit_repository,
        "insert",
        lambda actual_conn, **kwargs: audits.append({"conn": actual_conn, **kwargs}),
    )

    batch_service._watch_daily_batch(41, process)

    assert process.waited is True
    assert failed == [(41, "배치 프로세스가 완료 상태를 기록하지 않고 종료됨(exit_code=9)")]
    assert audits[0]["conn"] is conn
    assert audits[0]["action"] == "BATCH_RUN_COMPLETED"
    assert audits[0]["after_value"]["status"] == "FAILED"
    assert audits[0]["after_value"]["run_type"] == "MANUAL"


@pytest.mark.parametrize("terminal_status", ["SUCCESS", "FAILED"])
def test_watcher_is_noop_when_run_is_already_terminal(monkeypatch, terminal_status):
    process = FakeProcess(0)

    @contextmanager
    def fake_get_connection():
        yield object()

    monkeypatch.setattr(batch_service, "get_connection", fake_get_connection)
    monkeypatch.setattr(
        batch_service.batch_run_repository,
        "get",
        lambda conn, run_id: {
            "id": run_id,
            "run_type": "MANUAL",
            "status": terminal_status,
            "triggered_by": 17,
        },
    )
    monkeypatch.setattr(
        batch_service.batch_run_repository,
        "mark_failed",
        lambda *args: pytest.fail("terminal 상태를 다시 실패 처리하면 안 됩니다"),
    )
    monkeypatch.setattr(
        batch_service.audit_repository,
        "insert",
        lambda *args, **kwargs: pytest.fail("terminal 상태에 완료 감사를 중복 기록하면 안 됩니다"),
    )

    batch_service._watch_daily_batch(42, process)

    assert process.waited is True


class RowCountConnection:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount
        self.sql = ""
        self.params: tuple[Any, ...] = ()

    def execute(self, sql: str, params: tuple[Any, ...]) -> FakeCursor:
        self.sql = sql
        self.params = params
        return FakeCursor(rowcount=self.rowcount)


@pytest.mark.parametrize(("rowcount", "expected"), [(1, True), (0, False)])
def test_api_mark_failed_is_fenced_and_returns_rowcount(rowcount, expected):
    conn = RowCountConnection(rowcount)

    result = batch_run_repository.mark_failed(conn, 3, "safe reason")  # type: ignore[arg-type]

    assert result is expected
    assert "status = 'RUNNING'" in conn.sql
    assert conn.params == ("safe reason", 3)


@pytest.mark.parametrize(("rowcount", "expected"), [(1, True), (0, False)])
def test_batch_finish_run_is_fenced_and_returns_rowcount(rowcount, expected):
    conn = RowCountConnection(rowcount)

    result = batch_repository.finish_run(  # type: ignore[arg-type]
        conn,
        5,
        status="SUCCESS",
        failure_reason=None,
        params_snapshot={},
        stage_stats={},
        source_status=[],
    )

    assert result is expected
    assert "status = 'RUNNING'" in conn.sql
    assert conn.params[-1] == 5


def test_scheduled_daily_lock_miss_creates_no_run_or_stale_update(monkeypatch):
    @contextmanager
    def fake_acquire(lock_key: int):
        assert lock_key == advisory_lock.BATCH_MUTATION_LOCK_KEY
        yield False

    monkeypatch.setattr(run_daily, "setup_logging", lambda name: None)
    monkeypatch.setattr(run_daily, "acquire_advisory_lock", fake_acquire)
    monkeypatch.setattr(
        run_daily.repo,
        "fail_stale_runs",
        lambda *args: pytest.fail("잠금 없이 stale UPDATE를 실행하면 안 됩니다"),
    )
    monkeypatch.setattr(
        run_daily.repo,
        "create_scheduled_run",
        lambda *args: pytest.fail("잠금 없이 예약 실행 행을 만들면 안 됩니다"),
    )

    assert run_daily.run(date(2026, 10, 1), None) == 1


def test_manual_daily_lock_miss_conditionally_fails_and_audits(monkeypatch):
    conn = object()
    audits: list[dict[str, Any]] = []

    @contextmanager
    def fake_acquire(lock_key: int):
        yield False

    @contextmanager
    def fake_get_connection():
        yield conn

    monkeypatch.setattr(run_daily, "setup_logging", lambda name: None)
    monkeypatch.setattr(run_daily, "acquire_advisory_lock", fake_acquire)
    monkeypatch.setattr(run_daily, "get_connection", fake_get_connection)
    monkeypatch.setattr(
        run_daily.repo,
        "get_run",
        lambda actual_conn, run_id: {
            "id": run_id,
            "run_type": "MANUAL",
            "status": "RUNNING",
            "triggered_by": 23,
            "target_date": date(2026, 10, 1),
        },
    )
    monkeypatch.setattr(run_daily.repo, "finish_run", lambda *args, **kwargs: True)
    monkeypatch.setattr(run_daily.repo, "insert_audit", lambda actual_conn, **kwargs: audits.append(kwargs))

    assert run_daily.run(None, 71) == 1
    assert audits[0]["action"] == "BATCH_RUN_COMPLETED"
    assert audits[0]["after_value"]["status"] == "FAILED"
    assert audits[0]["after_value"]["run_type"] == "MANUAL"


def test_daily_finish_fencing_failure_skips_completion_audit(monkeypatch):
    conn = object()
    stale_calls: list[int] = []

    @contextmanager
    def fake_acquire(lock_key: int):
        yield True

    @contextmanager
    def fake_get_connection():
        yield conn

    monkeypatch.setattr(run_daily, "setup_logging", lambda name: None)
    monkeypatch.setattr(run_daily, "acquire_advisory_lock", fake_acquire)
    monkeypatch.setattr(run_daily, "get_connection", fake_get_connection)
    monkeypatch.setattr(run_daily, "get_settings", lambda: SimpleNamespace(batch_stale_minutes=180))
    monkeypatch.setattr(run_daily.repo, "fail_stale_runs", lambda actual_conn, minutes: stale_calls.append(minutes) or 0)
    monkeypatch.setattr(run_daily.repo, "create_scheduled_run", lambda actual_conn, target_date: 81)
    monkeypatch.setattr(
        run_daily.repo,
        "get_run",
        lambda actual_conn, run_id: {
            "id": run_id,
            "run_type": "SCHEDULED",
            "status": "RUNNING",
            "triggered_by": None,
            "target_date": date(2026, 10, 1),
        },
    )
    monkeypatch.setattr(run_daily, "run_pipeline", lambda target_date, run_id: ({}, [], {}, []))
    monkeypatch.setattr(run_daily.repo, "finish_run", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        run_daily.repo,
        "insert_audit",
        lambda *args, **kwargs: pytest.fail("finish가 거부되면 완료 감사를 기록하면 안 됩니다"),
    )

    assert run_daily.run(date(2026, 10, 1), None) == 1
    assert stale_calls == [180]


def test_trigger_popen_error_fails_and_audits_in_request_transaction(monkeypatch):
    now = datetime(2026, 10, 1, 8, 0, tzinfo=KST)
    row = {
        "id": 91,
        "run_type": "MANUAL",
        "status": "RUNNING",
        "target_date": date(2026, 10, 1),
        "requested_at": now,
        "started_at": None,
        "completed_at": None,
        "failure_reason": None,
        "triggered_by": 31,
        "triggered_by_name": "테스트 관리자",
        "source_status": [],
    }
    audits: list[dict[str, Any]] = []

    class FakeRequestConnection:
        committed = False

        def commit(self) -> None:
            self.committed = True

    conn = FakeRequestConnection()
    monkeypatch.setattr(batch_service, "_fail_stale_if_lock_available", lambda actual_conn: (True, 0))
    monkeypatch.setattr(batch_service.batch_run_repository, "running", lambda actual_conn: None)
    monkeypatch.setattr(batch_service, "cooldown_remaining_seconds", lambda actual_conn, user_id: 0)
    monkeypatch.setattr(batch_service.batch_run_repository, "create_manual_run", lambda *args: 91)
    monkeypatch.setattr(batch_service.audit_repository, "insert", lambda actual_conn, **kwargs: audits.append(kwargs))
    monkeypatch.setattr(batch_service, "_spawn_daily_batch", lambda run_id: (_ for _ in ()).throw(OSError("secret")))

    def mark_failed(actual_conn, run_id, reason):
        row.update(status="FAILED", completed_at=now, failure_reason=reason)
        return True

    monkeypatch.setattr(batch_service.batch_run_repository, "mark_failed", mark_failed)
    monkeypatch.setattr(batch_service.batch_run_repository, "get", lambda actual_conn, run_id: row)
    user = CurrentUser(id=31, role="HQ_MARKETING", branch_id=None)

    response = batch_service.trigger(conn, user)  # type: ignore[arg-type]

    assert conn.committed is True
    assert response.run.status == "FAILED"
    assert [audit["action"] for audit in audits] == ["BATCH_RUN_REQUESTED", "BATCH_RUN_COMPLETED"]
    assert audits[-1]["after_value"]["failure_reason"] == "배치 프로세스 기동 실패: OSError"
    assert "secret" not in audits[-1]["after_value"]["failure_reason"]


def test_monthly_lock_miss_exits_one_before_run_and_closes_after_unlock(monkeypatch):
    order: list[str] = []

    @contextmanager
    def fake_acquire(lock_key: int):
        order.append("lock_enter")
        yield False
        order.append("lock_exit")

    monkeypatch.setattr(run_monthly, "setup_logging", lambda name: None)
    monkeypatch.setattr(run_monthly, "acquire_advisory_lock", fake_acquire)
    monkeypatch.setattr(run_monthly, "run", lambda *args, **kwargs: pytest.fail("월간 데이터를 쓰면 안 됩니다"))
    monkeypatch.setattr(run_monthly, "close_pool", lambda: order.append("close_pool"))

    assert run_monthly.main([]) == 1
    assert order == ["lock_enter", "lock_exit", "close_pool"]


def test_geocode_lock_miss_is_successful_skip_and_closes_after_unlock(monkeypatch):
    order: list[str] = []

    @contextmanager
    def fake_acquire(lock_key: int):
        order.append("lock_enter")
        yield False
        order.append("lock_exit")

    monkeypatch.setattr(geocode_job, "setup_logging", lambda name: None)
    monkeypatch.setattr(geocode_job, "log_fields", lambda *args, **kwargs: None)
    monkeypatch.setattr(geocode_job, "acquire_advisory_lock", fake_acquire)
    monkeypatch.setattr(geocode_job, "run", lambda: pytest.fail("지오코딩 데이터를 쓰면 안 됩니다"))
    monkeypatch.setattr(geocode_job, "close_pool", lambda: order.append("close_pool"))

    assert geocode_job.main() == 0
    assert order == ["lock_enter", "lock_exit", "close_pool"]


def _source_status(source_name: str, status: str, *, delay_days: int = 0) -> dict[str, Any]:
    return {
        "source_name": source_name,
        "status": status,
        "as_of_date": date(2026, 10, 1),
        "expected_as_of": date(2026, 10, 1),
        "delay_days": delay_days,
        "is_fallback": status == "FALLBACK",
    }


@pytest.mark.parametrize(
    ("run_status", "sources", "list_ready", "expected_message"),
    [
        (
            "FAILED",
            [_source_status("PERMIT_DAILY", "UNAVAILABLE")],
            True,
            "오늘 일간 배치가 실패했습니다.",
        ),
        (
            "SUCCESS",
            [
                _source_status("PERMIT_DAILY", "UNAVAILABLE"),
                _source_status("KMA_WARNING", "DEGRADED"),
            ],
            True,
            "display-PERMIT_DAILY",
        ),
        (
            "SUCCESS",
            [
                _source_status("KMA_WARNING", "DEGRADED"),
                _source_status("ECOS_FX", "FALLBACK", delay_days=2),
            ],
            True,
            "display-KMA_WARNING",
        ),
        (
            "SUCCESS",
            [_source_status("ECOS_FX", "FALLBACK", delay_days=2)],
            True,
            "기준일 2일 전",
        ),
        (
            "SUCCESS",
            [_source_status("KMA_WARNING", "FRESH")],
            False,
            "오늘 추천 명부가 생성되지 않았습니다.",
        ),
    ],
)
def test_data_freshness_message_priority(
    monkeypatch, run_status, sources, list_ready, expected_message
):
    finished = {"status": run_status, "source_status": sources}
    monkeypatch.setattr(
        batch_service,
        "get_pipeline_config",
        lambda: SimpleNamespace(source_display_name=lambda name: f"display-{name}"),
    )
    monkeypatch.setattr(batch_service, "today_kst", lambda: date(2026, 10, 1))
    monkeypatch.setattr(
        batch_service.batch_run_repository,
        "latest_finished_for_date",
        lambda conn, day: finished,
    )
    monkeypatch.setattr(batch_service.batch_run_repository, "running", lambda conn: None)
    monkeypatch.setattr(
        batch_service.recommendation_repository,
        "has_list",
        lambda conn, day, branch_id: list_ready,
    )

    response = batch_service.get_data_freshness(
        object(), CurrentUser(id=1, role="BRANCH_MANAGER", branch_id=1)  # type: ignore[arg-type]
    )

    assert response.delayed is True
    assert expected_message in (response.message or "")


def test_api_stale_cleanup_uses_same_direct_session_for_lock_update_and_unlock(monkeypatch):
    lock_conn = FakeLockConnection(True)
    _patch_direct_connection(monkeypatch, lock_conn)
    monkeypatch.setattr(batch_service, "get_settings", lambda: SimpleNamespace(batch_stale_minutes=180))

    result = batch_service._fail_stale_if_lock_available(object())  # type: ignore[arg-type]

    assert result == (True, 0)
    assert "pg_try_advisory_lock" in lock_conn.statements[0][0]
    assert "UPDATE batch_run" in lock_conn.statements[1][0]
    assert lock_conn.statements[1][1] == (180,)
    assert "pg_advisory_unlock" in lock_conn.statements[2][0]
