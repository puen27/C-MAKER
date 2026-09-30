"""일간 배치 P0 안전 동작 회귀 테스트 — 외부망/실제 DB를 사용하지 않는다."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from backend.batch import batch_repository, run_daily
from backend.batch.connectors.http_client import FetchResult
from backend.common.config import KST, get_pipeline_config
from backend.common.schemas.brief import BriefContent, BriefInput
from backend.common.schemas.recommendation import RankedRecommendation, ScoredCandidate
from backend.common.snapshot_store import SnapshotRecord
from backend.tests.factories import TODAY, branch, fact, signal

CONFIG = get_pipeline_config()


@contextmanager
def _fake_connection():
    yield object()


def _outcome(
    source_name: str,
    *,
    status: str = "FRESH",
    as_of_date: date = TODAY,
    payload: Any | None = None,
) -> run_daily.SourceOutcome:
    return run_daily.SourceOutcome(
        source_name=source_name,
        status=status,
        expected_as_of=TODAY,
        snapshot_id=1,
        as_of_date=as_of_date,
        payload={} if payload is None else payload,
    )


def _thresholds() -> dict[str, batch_repository.ThresholdParam]:
    updated_at = datetime(2026, 9, 1, tzinfo=KST)
    return {
        name: batch_repository.ThresholdParam(
            id=index,
            signal_type=name,
            category="SYSTEM",
            threshold_value=value,
            unit="일" if "DAYS" in name else "건",
            updated_at=updated_at,
        )
        for index, (name, value) in enumerate(
            {
                "EVENT_COOLDOWN_DAYS": 14,
                "DAILY_EVENT_CAP": 8,
                "CONTACT_COOLDOWN_DAYS": 30,
            }.items(),
            start=1,
        )
    }


def test_fresh_old_as_of_reports_delay_without_becoming_fallback(monkeypatch):
    monkeypatch.setattr(run_daily, "get_connection", _fake_connection)
    monkeypatch.setattr(run_daily, "save_snapshot", lambda *args: 17)
    target_date = date(2026, 10, 10)

    outcome = run_daily.collect_source(
        "KMA_WARNING",
        target_date,
        CONFIG,
        lambda: (FetchResult(payload={"warnings": []}, request_params={}), target_date - timedelta(days=2)),
    )

    assert outcome.status == "FRESH"
    assert outcome.usable is True
    assert outcome.delay_days == 2
    assert outcome.to_status()["delay_days"] == 2


@pytest.mark.parametrize(
    ("fallback_age", "expected_status", "expected_usable"),
    [(3, "FALLBACK", True), (4, "UNAVAILABLE", False)],
)
def test_fallback_respects_source_max_age(monkeypatch, fallback_age, expected_status, expected_usable):
    monkeypatch.setattr(run_daily, "get_connection", _fake_connection)
    target_date = date(2026, 10, 10)
    expected_as_of = target_date - timedelta(days=CONFIG.sources["PERMIT_DAILY"].expected_lag_days)
    fallback = SnapshotRecord(
        id=31,
        source_name="PERMIT_DAILY",
        as_of_date=expected_as_of - timedelta(days=fallback_age),
        fetched_at=datetime(2026, 10, 9, tzinfo=KST),
        raw_payload={"rows": [{"safe": True}]},
    )
    monkeypatch.setattr(run_daily, "find_latest_snapshot", lambda *args: fallback)

    def fail_fetch():
        raise RuntimeError("api-key=secret raw-response=do-not-store")

    outcome = run_daily.collect_source("PERMIT_DAILY", target_date, CONFIG, fail_fetch)

    assert outcome.status == expected_status
    assert outcome.usable is expected_usable
    assert outcome.snapshot_id == 31
    assert outcome.as_of_date == fallback.as_of_date
    assert outcome.delay_days == fallback_age
    assert outcome.error == "RuntimeError"
    assert "secret" not in (outcome.error or "") + (outcome.note or "")
    if expected_status == "UNAVAILABLE":
        assert outcome.payload is None


def test_nts_fallback_applies_status_with_snapshot_as_of(monkeypatch):
    checked_dates: list[date] = []
    monkeypatch.setattr(run_daily, "get_connection", _fake_connection)
    monkeypatch.setattr(
        run_daily.repo,
        "update_business_status_by_nts",
        lambda conn, biz_no, status, checked_on: checked_dates.append(checked_on) or 1,
    )
    as_of_date = TODAY - timedelta(days=1)
    outcome = _outcome(
        "NTS_STATUS",
        status="FALLBACK",
        as_of_date=as_of_date,
        payload={"data": [{"b_no": "1234567890", "b_stt_cd": "01"}]},
    )

    assert run_daily.apply_nts_results(outcome) == {"updated": 1, "unknown": 0}
    assert checked_dates == [as_of_date]


def test_permit_and_nts_postprocessing_failures_are_isolated(monkeypatch):
    processed_branches: list[str] = []
    outcomes = {
        "PERMIT_DAILY": _outcome("PERMIT_DAILY", payload={"rows": []}),
        "KMA_WARNING": run_daily.SourceOutcome("KMA_WARNING", "SKIPPED", TODAY),
        "ECOS_FX": run_daily.SourceOutcome("ECOS_FX", "SKIPPED", TODAY),
        "OPINET_PRICE": run_daily.SourceOutcome("OPINET_PRICE", "SKIPPED", TODAY),
    }

    monkeypatch.setattr(run_daily, "get_connection", _fake_connection)
    monkeypatch.setattr(run_daily, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(run_daily, "create_llm_client", lambda settings: None)
    monkeypatch.setattr(run_daily.repo, "load_thresholds", lambda conn: _thresholds())
    monkeypatch.setattr(run_daily.repo, "load_signal_weights", lambda conn: [])
    monkeypatch.setattr(run_daily.repo, "load_effective_branches", lambda conn, reference_ts: [branch()])
    monkeypatch.setattr(run_daily, "collect_all_sources", lambda *args: outcomes)
    monkeypatch.setattr(
        run_daily,
        "apply_permit_changes",
        lambda *args: (_ for _ in ()).throw(ValueError("raw permit response")),
    )
    monkeypatch.setattr(
        run_daily,
        "collect_nts",
        lambda *args: (_outcome("NTS_STATUS", payload={"data": []}), 0),
    )
    monkeypatch.setattr(
        run_daily,
        "apply_nts_results",
        lambda *args: (_ for _ in ()).throw(LookupError("secret nts value")),
    )

    def normalize_branch(actual_branch, actual_outcomes, openings, config):
        assert actual_outcomes["PERMIT_DAILY"].status == "UNAVAILABLE"
        assert actual_outcomes["NTS_STATUS"].status == "UNAVAILABLE"
        processed_branches.append(actual_branch.branch_code)
        return [], []

    monkeypatch.setattr(run_daily, "normalize_for_branch", normalize_branch)
    monkeypatch.setattr(run_daily, "sense_branch", lambda *args: {"signals": 0})
    monkeypatch.setattr(
        run_daily,
        "process_branch_targeting",
        lambda *args: (run_daily.TargetingResult(stats={"skipped": "ALREADY_TAGGED"}), []),
    )

    stats, source_status, _params, failed = run_daily.run_pipeline(TODAY, 9)
    statuses = {item["source_name"]: item for item in source_status}

    assert processed_branches == ["000101"]
    assert failed == []
    assert stats["status_verification"]["permit"]["error"] == "ValueError"
    assert stats["status_verification"]["nts"]["error"] == "LookupError"
    assert stats["sources"]["unavailable"] == ["NTS_STATUS", "PERMIT_DAILY"]
    assert statuses["PERMIT_DAILY"]["error"] == "ValueError"
    assert statuses["NTS_STATUS"]["error"] == "LookupError"
    assert "raw permit response" not in str(stats) + str(source_status)
    assert "secret nts value" not in str(stats) + str(source_status)


def test_one_normalizer_failure_keeps_other_source_drafts(monkeypatch):
    weather_draft = signal(source_name="KMA_WARNING", signal_type="WEATHER_WARNING", target_key="WEATHER:호우")
    outcomes = {
        "PERMIT_DAILY": _outcome("PERMIT_DAILY", payload={"rows": []}),
        "KMA_WARNING": _outcome("KMA_WARNING", payload={"stations": {}}),
    }
    monkeypatch.setattr(
        run_daily.normalizer,
        "normalize_permit_openings",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("bad permit row")),
    )
    monkeypatch.setattr(
        run_daily.normalizer,
        "normalize_weather_warnings",
        lambda *args, **kwargs: [weather_draft],
    )

    drafts, failed_sources = run_daily.normalize_for_branch(branch(), outcomes, [], CONFIG)

    assert drafts == [weather_draft]
    assert failed_sources == ["PERMIT_DAILY"]


class _TransactionTracker:
    def __init__(self) -> None:
        self.connections: list[object] = []
        self.active = 0
        self.commits = 0
        self.rollbacks = 0
        self.order: list[str] = []

    @contextmanager
    def connection(self):
        conn = object()
        self.connections.append(conn)
        label = "plan" if len(self.connections) == 1 else "publish"
        self.order.append(f"{label}_enter")
        self.active += 1
        try:
            yield conn
        except Exception:
            self.rollbacks += 1
            self.order.append(f"{label}_rollback")
            raise
        else:
            self.commits += 1
            self.order.append(f"{label}_commit")
        finally:
            self.active -= 1


def _ranked() -> RankedRecommendation:
    return RankedRecommendation(
        candidate=ScoredCandidate(
            business_id=17,
            industry_code="I201",
            industry_name="음식",
            distance_km=0.3,
            signal_score=0.8,
            freshness_score=0.5,
            proximity=0.9,
            scale_fit=1.0,
            score=1.17,
            reason_tier="AREA",
        ),
        rank=1,
        is_exploration_slot=False,
    )


def _brief_job(recommendation_id: int = 0) -> run_daily.BriefJob:
    brief_fact = fact("가상 근거입니다.")
    return run_daily.BriefJob(
        branch_id=1,
        ranked=_ranked(),
        brief_input=BriefInput(
            recommendation_id=recommendation_id,
            branch_name="가상지점",
            business_name="가상사업체",
            industry_name="음식",
            distance_km=0.3,
            facts=[brief_fact],
        ),
        reason_summary="가상 선정 사유",
    )


def _brief_content(recommendation_id: int = 0) -> BriefContent:
    return BriefContent(
        recommendation_id=recommendation_id,
        reason_summary="가상 선정 사유",
        reason_facts=[fact("가상 근거입니다.")],
        talk_script=["안녕하세요."],
        checklist=["공개 정보 확인"],
        generation_status="TEMPLATE",
    )


def test_targeting_orders_plan_then_llm_without_transaction_then_atomic_publish(monkeypatch):
    tracker = _TransactionTracker()
    job = _brief_job()
    content = _brief_content()
    monkeypatch.setattr(run_daily, "get_connection", tracker.connection)

    def fake_target(actual_conn, *args):
        assert tracker.active == 1
        assert actual_conn is tracker.connections[0]
        tracker.order.append("target")
        return run_daily.TargetingResult(stats={"recommendations": 1}, brief_jobs=[job])

    def generate(jobs, llm, config):
        assert tracker.active == 0
        assert jobs == [job]
        tracker.order.append("llm")
        return [content]

    monkeypatch.setattr(run_daily, "target_branch", fake_target)
    monkeypatch.setattr(run_daily, "generate_briefs", generate)
    monkeypatch.setattr(run_daily.repo, "branch_has_tagged_recommendations", lambda *args: False)
    monkeypatch.setattr(
        run_daily.repo,
        "delete_recommendations",
        lambda conn, branch_id, day: tracker.order.append("delete") or 1,
    )
    monkeypatch.setattr(
        run_daily.repo,
        "insert_recommendation",
        lambda conn, **kwargs: tracker.order.append("insert_recommendation") or 41,
    )

    def insert_brief(conn, brief):
        assert conn is tracker.connections[1]
        assert brief.recommendation_id == 41
        tracker.order.append("insert_brief")

    monkeypatch.setattr(run_daily.repo, "insert_brief", insert_brief)

    def count_completeness(conn, recommendation_ids):
        assert conn is tracker.connections[1]
        assert recommendation_ids == [41]
        tracker.order.append("complete")
        return 1, 1

    monkeypatch.setattr(run_daily.repo, "count_brief_completeness", count_completeness)

    _targeting, briefs = run_daily.process_branch_targeting(
        branch(), TODAY, _thresholds(), SimpleNamespace(), CONFIG, 7, None
    )

    assert briefs[0].recommendation_id == 41
    assert tracker.order == [
        "plan_enter",
        "target",
        "plan_commit",
        "llm",
        "publish_enter",
        "delete",
        "insert_recommendation",
        "insert_brief",
        "complete",
        "publish_commit",
    ]
    assert tracker.commits == 2
    assert tracker.rollbacks == 0


def test_brief_generation_failure_never_opens_publish_or_deletes_existing_list(monkeypatch):
    tracker = _TransactionTracker()
    monkeypatch.setattr(run_daily, "get_connection", tracker.connection)
    monkeypatch.setattr(
        run_daily,
        "target_branch",
        lambda actual_conn, *args: run_daily.TargetingResult(
            stats={"recommendations": 1}, brief_jobs=[_brief_job()]
        ),
    )
    monkeypatch.setattr(
        run_daily,
        "generate_briefs",
        lambda *args: (_ for _ in ()).throw(RuntimeError("brief write failed")),
    )
    monkeypatch.setattr(
        run_daily.repo,
        "delete_recommendations",
        lambda *args: pytest.fail("브리프 생성 실패 시 기존 명부를 삭제하면 안 됩니다"),
    )

    with pytest.raises(RuntimeError, match="brief write failed"):
        run_daily.process_branch_targeting(
            branch(), TODAY, _thresholds(), SimpleNamespace(), CONFIG, 7, None
        )

    assert len(tracker.connections) == 1
    assert tracker.commits == 1
    assert tracker.rollbacks == 0


def test_brief_insert_failure_rolls_back_publish_transaction(monkeypatch):
    tracker = _TransactionTracker()
    monkeypatch.setattr(run_daily, "get_connection", tracker.connection)
    monkeypatch.setattr(
        run_daily,
        "target_branch",
        lambda actual_conn, *args: run_daily.TargetingResult(
            stats={"recommendations": 1}, brief_jobs=[_brief_job()]
        ),
    )
    monkeypatch.setattr(run_daily, "generate_briefs", lambda *args: [_brief_content()])
    monkeypatch.setattr(run_daily.repo, "branch_has_tagged_recommendations", lambda *args: False)
    monkeypatch.setattr(run_daily.repo, "delete_recommendations", lambda *args: 1)
    monkeypatch.setattr(run_daily.repo, "insert_recommendation", lambda *args, **kwargs: 41)
    monkeypatch.setattr(
        run_daily.repo,
        "insert_brief",
        lambda *args: (_ for _ in ()).throw(RuntimeError("brief insert failed")),
    )

    with pytest.raises(RuntimeError, match="brief insert failed"):
        run_daily.process_branch_targeting(
            branch(), TODAY, _thresholds(), SimpleNamespace(), CONFIG, 7, None
        )

    assert tracker.commits == 1
    assert tracker.rollbacks == 1


def test_completeness_mismatch_rolls_back_publish_transaction(monkeypatch):
    tracker = _TransactionTracker()
    monkeypatch.setattr(run_daily, "get_connection", tracker.connection)
    monkeypatch.setattr(
        run_daily,
        "target_branch",
        lambda actual_conn, *args: run_daily.TargetingResult(
            stats={"recommendations": 1}, brief_jobs=[_brief_job()]
        ),
    )
    monkeypatch.setattr(run_daily, "generate_briefs", lambda *args: [_brief_content()])
    monkeypatch.setattr(run_daily.repo, "branch_has_tagged_recommendations", lambda *args: False)
    monkeypatch.setattr(run_daily.repo, "delete_recommendations", lambda *args: 1)
    monkeypatch.setattr(run_daily.repo, "insert_recommendation", lambda *args, **kwargs: 41)
    monkeypatch.setattr(run_daily.repo, "insert_brief", lambda *args: None)
    monkeypatch.setattr(run_daily.repo, "count_brief_completeness", lambda *args: (1, 0))

    with pytest.raises(RuntimeError, match="완전성 검증 실패"):
        run_daily.process_branch_targeting(
            branch(), TODAY, _thresholds(), SimpleNamespace(), CONFIG, 7, None
        )

    assert tracker.commits == 1
    assert tracker.rollbacks == 1


def test_tag_race_discards_plan_without_deleting_existing_list(monkeypatch):
    tracker = _TransactionTracker()
    monkeypatch.setattr(run_daily, "get_connection", tracker.connection)
    monkeypatch.setattr(
        run_daily,
        "target_branch",
        lambda actual_conn, *args: run_daily.TargetingResult(
            stats={"recommendations": 1}, brief_jobs=[_brief_job()]
        ),
    )
    monkeypatch.setattr(run_daily, "generate_briefs", lambda *args: [_brief_content()])
    monkeypatch.setattr(run_daily.repo, "branch_has_tagged_recommendations", lambda *args: True)
    monkeypatch.setattr(run_daily.repo, "count_missing_branch_briefs", lambda *args: 0)
    monkeypatch.setattr(
        run_daily.repo,
        "delete_recommendations",
        lambda *args: pytest.fail("태깅 race 이후 기존 명부를 삭제하면 안 됩니다"),
    )

    targeting, briefs = run_daily.process_branch_targeting(
        branch(), TODAY, _thresholds(), SimpleNamespace(), CONFIG, 7, None
    )

    assert targeting.stats["skipped"] == "ALREADY_TAGGED"
    assert targeting.stats["discarded_plan"] == 1
    assert briefs == []
    assert tracker.commits == 2
    assert tracker.rollbacks == 0


def test_empty_effective_branches_fail_before_connectors(monkeypatch):
    monkeypatch.setattr(run_daily, "get_connection", _fake_connection)
    monkeypatch.setattr(run_daily, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(run_daily.repo, "load_thresholds", lambda conn: {})
    monkeypatch.setattr(run_daily.repo, "load_signal_weights", lambda conn: [])
    monkeypatch.setattr(run_daily.repo, "load_effective_branches", lambda conn, reference_ts: [])
    monkeypatch.setattr(
        run_daily,
        "collect_all_sources",
        lambda *args: pytest.fail("효력 지점 0건이면 connector를 호출하면 안 됩니다"),
    )

    with pytest.raises(RuntimeError, match="효력 발생 지점이 0건"):
        run_daily.run_pipeline(TODAY, 11)


class _QueryCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class _QueryConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.sql = ""
        self.params: tuple[Any, ...] = ()

    def execute(self, sql: str, params: tuple[Any, ...]) -> _QueryCursor:
        self.sql = sql
        self.params = params
        return _QueryCursor(self.rows)


def test_cooldown_sql_uses_latest_activity_for_select_filter_and_sort():
    activity_date = TODAY - timedelta(days=1)
    conn = _QueryConnection(
        [{"id": 3, "signal_type": "AREA_NEW_OPENINGS", "target_key": "AREA", "occurred_on": activity_date}]
    )

    events = batch_repository.load_cooldown_events(conn, 1, TODAY - timedelta(days=14))  # type: ignore[arg-type]

    assert events[0].occurred_on == activity_date
    assert conn.sql.count("GREATEST(occurred_on, COALESCE(last_merged_on, occurred_on))") == 3
    assert ">= %s" in conn.sql
    assert "ORDER BY GREATEST" in conn.sql


@pytest.mark.parametrize(
    ("run_type", "finished_at", "applicable", "met", "missed_by_seconds"),
    [
        ("SCHEDULED", datetime(2026, 9, 29, 7, 29, tzinfo=KST), True, True, 0.0),
        ("SCHEDULED", datetime(2026, 9, 29, 7, 30, 45, tzinfo=KST), True, False, 45.0),
        ("MANUAL", datetime(2026, 9, 29, 9, 0, tzinfo=KST), False, None, None),
    ],
)
def test_calculate_sla_stats(run_type, finished_at, applicable, met, missed_by_seconds):
    result = run_daily.calculate_sla_stats(TODAY, run_type, finished_at)

    assert result["applicable"] is applicable
    assert result["finished_at"] == finished_at.isoformat()
    assert result["met"] is met
    assert result["missed_by_seconds"] == missed_by_seconds
    if applicable:
        assert result["deadline"] == datetime(2026, 9, 29, 7, 30, tzinfo=KST).isoformat()
    else:
        assert result["deadline"] is None


def test_daily_source_fallback_age_limits_are_configured():
    assert {
        name: source.options["max_fallback_age_days"]
        for name, source in CONFIG.sources.items()
        if name in {"PERMIT_DAILY", "NTS_STATUS", "KMA_WARNING", "ECOS_FX", "OPINET_PRICE"}
    } == {
        "PERMIT_DAILY": 3,
        "NTS_STATUS": 1,
        "KMA_WARNING": 1,
        "ECOS_FX": 7,
        "OPINET_PRICE": 2,
    }


def test_already_tagged_branch_fails_when_any_brief_is_missing(monkeypatch):
    conn = object()
    monkeypatch.setattr(run_daily.repo, "branch_has_tagged_recommendations", lambda *args: True)
    monkeypatch.setattr(run_daily.repo, "count_missing_branch_briefs", lambda *args: 1)

    with pytest.raises(RuntimeError, match="ALREADY_TAGGED.*브리프 1건"):
        run_daily.target_branch(
            conn, branch(), TODAY, _thresholds(), SimpleNamespace(), CONFIG, 7  # type: ignore[arg-type]
        )


def test_empty_candidates_preserve_existing_recommendations(monkeypatch):
    conn = object()
    monkeypatch.setattr(run_daily.repo, "branch_has_tagged_recommendations", lambda *args: False)
    monkeypatch.setattr(run_daily.repo, "load_candidates", lambda *args: [])
    monkeypatch.setattr(
        run_daily.repo,
        "delete_recommendations",
        lambda *args: pytest.fail("후보 0건이면 기존 명부를 삭제하면 안 됩니다"),
    )

    with pytest.raises(RuntimeError, match="추천 후보가 0건"):
        run_daily.target_branch(
            conn, branch(), TODAY, _thresholds(), SimpleNamespace(), CONFIG, 7  # type: ignore[arg-type]
        )


def test_effective_branches_without_coordinates_fail_before_connectors(monkeypatch):
    monkeypatch.setattr(run_daily, "get_connection", _fake_connection)
    monkeypatch.setattr(run_daily, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(run_daily.repo, "load_thresholds", lambda conn: _thresholds())
    monkeypatch.setattr(run_daily.repo, "load_signal_weights", lambda conn: [])
    monkeypatch.setattr(
        run_daily.repo,
        "load_effective_branches",
        lambda conn, reference_ts: [branch(lat=None, lng=None)],
    )
    monkeypatch.setattr(
        run_daily,
        "collect_all_sources",
        lambda *args: pytest.fail("좌표 보유 지점 0건이면 connector를 호출하면 안 됩니다"),
    )

    with pytest.raises(RuntimeError, match="좌표 보유 효력 지점이 0건"):
        run_daily.run_pipeline(TODAY, 12)


def test_normalizer_failure_marks_source_degraded_and_branch_failed_but_continues(monkeypatch):
    outcomes = {
        "PERMIT_DAILY": _outcome("PERMIT_DAILY", payload={"rows": []}),
        "KMA_WARNING": _outcome("KMA_WARNING", payload={"warnings": []}),
        "ECOS_FX": run_daily.SourceOutcome("ECOS_FX", "SKIPPED", TODAY),
        "OPINET_PRICE": run_daily.SourceOutcome("OPINET_PRICE", "SKIPPED", TODAY),
    }
    branches = [branch(), branch(id=2, branch_code="000102")]
    processed: list[str] = []

    monkeypatch.setattr(run_daily, "get_connection", _fake_connection)
    monkeypatch.setattr(run_daily, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(run_daily, "create_llm_client", lambda settings: None)
    monkeypatch.setattr(run_daily.repo, "load_thresholds", lambda conn: _thresholds())
    monkeypatch.setattr(run_daily.repo, "load_signal_weights", lambda conn: [])
    monkeypatch.setattr(run_daily.repo, "load_effective_branches", lambda conn, reference_ts: branches)
    monkeypatch.setattr(run_daily, "collect_all_sources", lambda *args: outcomes)
    monkeypatch.setattr(run_daily, "apply_permit_changes", lambda *args: ([], {}))
    monkeypatch.setattr(
        run_daily,
        "collect_nts",
        lambda *args: (run_daily.SourceOutcome("NTS_STATUS", "SKIPPED", TODAY), 0),
    )
    monkeypatch.setattr(run_daily, "apply_nts_results", lambda *args: {})

    def normalize(actual_branch, *args):
        if actual_branch.branch_code == "000101":
            return [], ["KMA_WARNING", "KMA_WARNING"]
        return [], []

    monkeypatch.setattr(run_daily, "normalize_for_branch", normalize)
    monkeypatch.setattr(run_daily, "sense_branch", lambda actual_branch, *args: {"signals": 0})

    def process(actual_branch, *args):
        processed.append(actual_branch.branch_code)
        return run_daily.TargetingResult(stats={"skipped": "ALREADY_TAGGED"}), []

    monkeypatch.setattr(run_daily, "process_branch_targeting", process)

    stats, source_status, _params, failed = run_daily.run_pipeline(TODAY, 9)
    statuses = {item["source_name"]: item for item in source_status}

    assert processed == ["000101", "000102"]
    assert failed == ["000101"]
    assert outcomes["KMA_WARNING"].usable is True
    assert statuses["KMA_WARNING"]["status"] == "DEGRADED"
    assert statuses["KMA_WARNING"]["note"] == "일부 지점의 소스 정규화에 실패했습니다."
    assert stats["normalization"]["000101"]["failed_sources"] == ["KMA_WARNING", "KMA_WARNING"]
    assert stats["normalization"]["000102"]["failed_sources"] == []
    assert stats["sources"]["degraded"] == ["KMA_WARNING"]
