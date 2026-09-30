"""일간 배치 진입점 — 07:30 SLA 파이프라인 (UC-03, UC-04, REQ-05, REQ-06).

    connectors(원본 수집 + 스냅샷 적재, 장애 시 전일 스냅샷 폴백)
      → 사업자 상태 검증(인허가 영업상태 1차, 국세청 2차 보완)
      → normalizers(SIGNAL 정규화) → sensing(EVENT 승격)
      → targeting(배제 → 스코어링 → TOP 20) → briefing(브리프 생성) → DB 적재

실행
  예약(cron 06:00): python -m backend.batch.run_daily [--date YYYY-MM-DD]
  수동(REQ-17):     API가 BATCH_RUN(RUNNING) 행을 만든 뒤 `--run-id N`으로 기동한다.

수동/예약 구분은 BATCH_RUN 기록에만 있고, 파이프라인 내부 흐름은 동일하다(5-arch-diagram.md §2).
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from typing import Any

import psycopg

from backend.batch import batch_repository as repo
from backend.batch.briefing.brief_generator import PROMPT_VERSION, generate_brief
from backend.batch.briefing.fact_builder import build_reason_facts
from backend.batch.briefing.llm_client import LlmClient, create_llm_client
from backend.batch.connectors import (
    ecos_connector,
    kma_connector,
    nts_connector,
    opinet_connector,
    permit_connector,
)
from backend.batch.connectors.http_client import FetchResult, SourceNotConfiguredError
from backend.batch.normalizers import signal_normalizer as normalizer
from backend.batch.normalizers.permit_parser import parse_permit_row
from backend.batch.population.business_loader import AreaIndex, apply_permit_records
from backend.batch.sensing.event_promoter import decide_promotions
from backend.batch.targeting.exclusion import ExclusionParams, apply_exclusions
from backend.batch.targeting.exploration import assemble_recommendations, exploration_seed
from backend.batch.targeting.scorer import WeightTable, score_candidates
from backend.common.config import (
    KST,
    PIPELINE_CONFIG_PATH,
    PipelineConfig,
    get_pipeline_config,
    get_settings,
    today_kst,
)
from backend.common.db.pool import close_pool, get_connection
from backend.common.geo import bounding_box, extract_sido, haversine_km
from backend.common.log_setup import log_fields, setup_logging
from backend.common.schemas.branch import BranchContext
from backend.common.schemas.brief import BriefContent, BriefInput
from backend.common.schemas.event import SignalDecision
from backend.common.schemas.signal import SignalDraft
from backend.common.snapshot_store import find_latest_snapshot, save_snapshot

logger = logging.getLogger("daily")

SLA_TIME = dt_time(7, 30)
NTS_STATUS_MAP = {"01": "정상", "02": "휴업", "03": "폐업"}


# ─────────────────────────── 소스 수집 + 폴백 ───────────────────────────


@dataclass
class SourceOutcome:
    source_name: str
    status: str  # FRESH / FALLBACK / UNAVAILABLE / SKIPPED
    expected_as_of: date
    snapshot_id: int | None = None
    as_of_date: date | None = None
    payload: Any = None
    error: str | None = None
    note: str | None = None

    @property
    def usable(self) -> bool:
        return self.snapshot_id is not None and self.payload is not None and self.as_of_date is not None

    @property
    def delay_days(self) -> int:
        """RULE-SENSE-04 지연 배지 — 수집 실패로 과거 스냅샷을 쓴 경우의 기준일 지연."""
        if self.status == "FALLBACK" and self.as_of_date is not None:
            return max(0, (self.expected_as_of - self.as_of_date).days)
        return 0

    def to_status(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "status": self.status,
            "expected_as_of": self.expected_as_of.isoformat(),
            "as_of_date": self.as_of_date.isoformat() if self.as_of_date else None,
            "snapshot_id": self.snapshot_id,
            "delay_days": self.delay_days,
            "is_fallback": self.status == "FALLBACK",
            "error": self.error,
            "note": self.note,
        }


def collect_source(
    source_name: str,
    target_date: date,
    config: PipelineConfig,
    fetch: Callable[[], tuple[FetchResult, date]],
) -> SourceOutcome:
    """소스 1개 수집. 어떤 예외도 배치 전체로 전파하지 않고 전일 스냅샷으로 폴백한다(OPS-04, RULE-SENSE-04)."""
    expected = target_date - timedelta(days=config.sources[source_name].expected_lag_days)
    started = time.monotonic()
    try:
        result, as_of = fetch()
        with get_connection() as conn:
            snapshot_id = save_snapshot(conn, source_name, as_of, result.payload, result.request_params)
        log_fields(logger, logging.INFO, "소스 수집", source=source_name, snapshot_id=snapshot_id,
                   as_of=as_of.isoformat(), elapsed_s=round(time.monotonic() - started, 2))
        return SourceOutcome(source_name, "FRESH", expected, snapshot_id, as_of, result.payload)
    except Exception as exc:  # noqa: BLE001 — 소스별 실패 격리
        error = f"{type(exc).__name__}: {exc}"[:300]
        level = logging.WARNING if isinstance(exc, SourceNotConfiguredError) else logging.ERROR
        with get_connection() as conn:
            fallback = find_latest_snapshot(conn, source_name, target_date)
        if fallback is None:
            log_fields(logger, level, "소스 수집 실패 — 폴백 스냅샷 없음", source=source_name, error=error)
            return SourceOutcome(source_name, "UNAVAILABLE", expected, error=error)
        log_fields(logger, level, "소스 수집 실패 — 전일 스냅샷 폴백", source=source_name, error=error,
                   fallback_snapshot_id=fallback.id, fallback_as_of=fallback.as_of_date.isoformat())
        return SourceOutcome(source_name, "FALLBACK", expected, fallback.id, fallback.as_of_date,
                             fallback.raw_payload, error=error)


def collect_nts(
    branches: list[BranchContext], target_date: date, config: PipelineConfig
) -> tuple[SourceOutcome, int]:
    """국세청 보완 검증 — 사업자번호가 있는 사업체만 1회 100건씩 조회한다(UC-03)."""
    settings = get_settings()
    source = config.sources["NTS_STATUS"]
    numbers: set[str] = set()
    missing = 0
    with get_connection() as conn:
        for branch in branches:
            box = bounding_box(branch.lat, branch.lng, branch.coverage_radius_km)  # type: ignore[arg-type]
            found, skipped = repo.list_biz_reg_nos_in_box(conn, *box)
            numbers.update(found)
            missing += skipped
    log_fields(logger, logging.INFO, "국세청 조회 대상", with_biz_reg_no=len(numbers),
               skipped_without_biz_reg_no=missing)
    if not numbers:
        return SourceOutcome("NTS_STATUS", "SKIPPED", target_date, note="사업자번호 확보 건 없음"), missing

    def fetch() -> tuple[FetchResult, date]:
        chunk_size = min(int(source.options.get("chunk_size", 100)), nts_connector.MAX_NUMBERS_PER_CALL)
        ordered = sorted(numbers)
        data: list[Any] = []
        for start in range(0, len(ordered), chunk_size):
            result = nts_connector.fetch_business_status(
                settings.data_go_kr_service_key, source.url, ordered[start : start + chunk_size]
            )
            data.extend(result.payload.get("data") or [])
        return FetchResult(payload={"data": data}, request_params={"url": source.url, "count": len(ordered)}), target_date

    return collect_source("NTS_STATUS", target_date, config, fetch), missing


def collect_all_sources(
    branches: list[BranchContext], target_date: date, config: PipelineConfig
) -> dict[str, SourceOutcome]:
    settings = get_settings()
    sources = config.sources
    outcomes: dict[str, SourceOutcome] = {}

    permit = sources["PERMIT_DAILY"]
    change_date = target_date - timedelta(days=permit.expected_lag_days)
    outcomes["PERMIT_DAILY"] = collect_source(
        "PERMIT_DAILY",
        target_date,
        config,
        lambda: (
            permit_connector.fetch_daily_changes(
                settings.data_go_kr_service_key, permit.url, change_date,
                page_size=int(permit.options.get("page_size", 500)),
            ),
            change_date,
        ),
    )

    station_ids = sorted(
        {sid for b in branches if (sid := config.kma_station_by_sido.get(extract_sido(b.address) or "")) is not None}
    )
    if station_ids:
        kma = sources["KMA_WARNING"]
        outcomes["KMA_WARNING"] = collect_source(
            "KMA_WARNING",
            target_date,
            config,
            lambda: (
                kma_connector.fetch_weather_warnings(
                    settings.data_go_kr_service_key, kma.url, station_ids=station_ids, target_date=target_date
                ),
                target_date,
            ),
        )
    else:
        outcomes["KMA_WARNING"] = SourceOutcome("KMA_WARNING", "SKIPPED", target_date, note="관할 관서 매핑 없음")

    ecos = sources["ECOS_FX"]

    def fetch_ecos() -> tuple[FetchResult, date]:
        options = ecos.options
        result = ecos_connector.fetch_exchange_rates(
            settings.ecos_api_key, ecos.url,
            stat_code=str(options["stat_code"]), item_code=str(options["item_code"]), cycle=str(options["cycle"]),
            start=target_date - timedelta(days=int(options.get("lookback_days", 10))), end=target_date,
        )
        fx = normalizer.compute_fx_change(result.payload)
        return result, (fx["as_of"] if fx else target_date - timedelta(days=1))

    outcomes["ECOS_FX"] = collect_source("ECOS_FX", target_date, config, fetch_ecos)

    opinet = sources["OPINET_PRICE"]
    outcomes["OPINET_PRICE"] = collect_source(
        "OPINET_PRICE",
        target_date,
        config,
        lambda: (
            opinet_connector.fetch_sido_average_prices(
                settings.opinet_api_key, opinet.url, prodcd=str(opinet.options.get("prodcd", "B027"))
            ),
            target_date,
        ),
    )
    return outcomes


# ─────────────────────────── 사업자 상태 검증 (UC-03) ───────────────────────────


def apply_permit_changes(
    outcome: SourceOutcome, area: AreaIndex, config: PipelineConfig
) -> tuple[list[normalizer.OpeningInfo], dict[str, int]]:
    if not outcome.usable:
        return [], {}
    assert outcome.as_of_date is not None
    window = int(config.sources["PERMIT_DAILY"].options.get("new_opening_window_days", 7))
    permits = [record for record in (parse_permit_row(row) for row in outcome.payload.get("rows") or []) if record]
    with get_connection() as conn:
        result = apply_permit_records(
            conn, permits, area, outcome.as_of_date,
            new_opening_since=outcome.as_of_date - timedelta(days=window),
        )
    openings = [
        normalizer.OpeningInfo(
            business_id=business_id, name=record.name, industry_name=record.industry_name,
            licensed_on=record.licensed_on, lat=record.lat, lng=record.lng,  # type: ignore[arg-type]
        )
        for business_id, _permit, record in result.new_openings
    ]
    return openings, result.as_dict()


def apply_nts_results(outcome: SourceOutcome, target_date: date) -> dict[str, int]:
    """국세청 조회 결과는 인허가 영업상태를 덮어쓴다(RULE-TARGET-01)."""
    if not outcome.usable:
        return {}
    updated = unknown = 0
    with get_connection() as conn:
        for item in outcome.payload.get("data") or []:
            status = NTS_STATUS_MAP.get(str(item.get("b_stt_cd") or ""))
            biz_no = str(item.get("b_no") or "").replace("-", "")
            if status is None or len(biz_no) != 10:
                unknown += 1
                continue
            updated += repo.update_business_status_by_nts(conn, biz_no, status, target_date)
    return {"updated": updated, "unknown": unknown}


# ─────────────────────────── 정규화 + 이벤트 승격 ───────────────────────────


def normalize_for_branch(
    branch: BranchContext,
    outcomes: dict[str, SourceOutcome],
    openings: list[normalizer.OpeningInfo],
    config: PipelineConfig,
) -> list[SignalDraft]:
    drafts: list[SignalDraft] = []
    permit = outcomes.get("PERMIT_DAILY")
    if permit and permit.usable:
        drafts += normalizer.normalize_permit_openings(
            branch, openings, snapshot_id=permit.snapshot_id, as_of_date=permit.as_of_date,  # type: ignore[arg-type]
            config=config.normalization,
        )
    kma = outcomes.get("KMA_WARNING")
    if kma and kma.usable:
        drafts += normalizer.normalize_weather_warnings(
            branch, kma.payload, snapshot_id=kma.snapshot_id, config=config  # type: ignore[arg-type]
        )
    ecos = outcomes.get("ECOS_FX")
    if ecos and ecos.usable:
        fx = normalizer.compute_fx_change(ecos.payload)
        if fx:
            drafts += normalizer.normalize_fx(branch, fx, snapshot_id=ecos.snapshot_id,  # type: ignore[arg-type]
                                              config=config.normalization)
    opinet = outcomes.get("OPINET_PRICE")
    if opinet and opinet.usable:
        drafts += normalizer.normalize_oil_price(
            branch, opinet.payload, snapshot_id=opinet.snapshot_id,  # type: ignore[arg-type]
            as_of_date=opinet.as_of_date, config=config,  # type: ignore[arg-type]
        )
    return drafts


def persist_decisions(
    conn: psycopg.Connection,
    branch: BranchContext,
    decisions: list[SignalDecision],
    target_date: date,
    run_id: int | None,
) -> dict[str, int]:
    counts = {"BELOW_THRESHOLD": 0, "MERGED": 0, "PROMOTED": 0, "TRIMMED": 0}
    event_by_key: dict[str, int] = {}
    for decision in decisions:
        if decision.outcome in ("PROMOTED", "TRIMMED"):
            signal = decision.signal
            reason = (f"{signal.signal_type}: {signal.raw_value:g}{signal.unit} > 임계치 "
                      f"{decision.threshold_value:g}{signal.unit}")
            event_by_key[decision.event_key] = repo.insert_event(
                conn, branch_id=branch.id, draft=signal, promotion_reason=reason, occurred_on=target_date,
                score=decision.event_score, status="ACTIVE" if decision.outcome == "PROMOTED" else "TRIMMED",
                batch_run_id=run_id,
            )
    for decision in decisions:
        counts[decision.outcome] += 1
        event_id: int | None = None
        if decision.outcome in ("PROMOTED", "TRIMMED"):
            event_id = event_by_key[decision.event_key]
        elif decision.outcome == "MERGED":
            event_id = decision.merged_event_id or event_by_key.get(decision.merge_into_batch_key or "")
            if decision.merged_event_id is not None:
                repo.mark_event_merged(conn, decision.merged_event_id, target_date, decision.signal.as_of_date)
        repo.insert_signal(conn, decision.signal, run_id, event_id)
    return counts


def sense_branch(
    branch: BranchContext,
    drafts: list[SignalDraft],
    target_date: date,
    thresholds: dict[str, repo.ThresholdParam],
    weights: WeightTable,
    run_id: int | None,
) -> dict[str, int]:
    cooldown_days = int(thresholds["EVENT_COOLDOWN_DAYS"].threshold_value)
    daily_cap = int(thresholds["DAILY_EVENT_CAP"].threshold_value)
    signal_thresholds = {k: v.threshold_value for k, v in thresholds.items() if v.category == "SIGNAL"}
    with get_connection() as conn:
        # 같은 스냅샷으로 이미 만든 신호는 재판정하지 않는다(수동 재실행 멱등성).
        new_drafts = [draft for draft in drafts if not repo.signal_exists(conn, draft)]
        decisions = decide_promotions(
            new_drafts,
            thresholds=signal_thresholds,
            existing_events=repo.load_cooldown_events(conn, branch.id, target_date - timedelta(days=cooldown_days)),
            active_today=repo.count_active_events_on(conn, branch.id, target_date),
            daily_cap=daily_cap,
            cooldown_days=cooldown_days,
            target_date=target_date,
            signal_weights=weights.global_weights(),
        )
        counts = persist_decisions(conn, branch, decisions, target_date, run_id)
    return {"signals": len(new_drafts), "reused": len(drafts) - len(new_drafts), **counts}


# ─────────────────────────── 명부 (배제 → 스코어링 → TOP 20) ───────────────────────────


@dataclass
class BriefJob:
    branch_id: int
    brief_input: BriefInput
    reason_summary: str


@dataclass
class TargetingResult:
    stats: dict[str, Any] = field(default_factory=dict)
    brief_jobs: list[BriefJob] = field(default_factory=list)


def target_branch(
    branch: BranchContext,
    target_date: date,
    thresholds: dict[str, repo.ThresholdParam],
    weights: WeightTable,
    config: PipelineConfig,
    run_id: int | None,
) -> TargetingResult:
    result = TargetingResult()
    with get_connection() as conn:
        if repo.branch_has_tagged_recommendations(conn, branch.id, target_date):
            # 이미 태깅이 시작된 명부는 재생성하지 않는다(태깅 이력 보존).
            result.stats = {"skipped": "ALREADY_TAGGED"}
            return result

        candidates = []
        for row in repo.load_candidates(conn, branch):
            distance = haversine_km(branch.lat, branch.lng, row["lat"], row["lng"])  # type: ignore[arg-type]
            if distance <= branch.coverage_radius_km:
                candidates.append(repo.to_candidate(row, round(distance, 3)))
        ids = [candidate.id for candidate in candidates]

        # ① 배제 (스코어링 이전 — 순서 고정, CLAUDE.md §3)
        params = ExclusionParams(
            contact_cooldown_days=int(thresholds["CONTACT_COOLDOWN_DAYS"].threshold_value),
            reject_exclusion_days=config.exclusion.reject_exclusion_days,
        )
        passed, excluded = apply_exclusions(candidates, repo.load_tag_history(conn, ids), target_date, params)

        # ② 스코어링
        lookback = config.scoring.event_lookback_days
        events = repo.load_scoring_events(conn, branch.id, target_date - timedelta(days=lookback - 1), target_date)
        scored = score_candidates(
            branch, passed, events, weights,
            repo.load_last_exposure(conn, branch.id, [c.id for c in passed], target_date), target_date, config,
        )

        # ③ TOP 20 (그중 3건 탐색 슬롯 — Phase 2 전까지 비활성)
        rec_config = config.recommendation
        ranked = assemble_recommendations(
            scored, top_n=rec_config.top_n, exploration_slots=rec_config.exploration_slots,
            exploration_enabled=rec_config.exploration_enabled, weights=weights,
            seed=exploration_seed(branch.id, target_date),
        )

        repo.delete_recommendations(conn, branch.id, target_date)
        candidates_by_id = {candidate.id: candidate for candidate in passed}
        events_by_id = {event.event_id: event for event in events}
        for item in ranked:
            recommendation_id = repo.insert_recommendation(
                conn, branch_id=branch.id, day=target_date, ranked=item, batch_run_id=run_id
            )
            candidate = candidates_by_id[item.candidate.business_id]
            reason_facts = build_reason_facts(candidate, item.candidate, events_by_id, config)
            result.brief_jobs.append(
                BriefJob(
                    branch_id=branch.id,
                    brief_input=BriefInput(
                        recommendation_id=recommendation_id, branch_name=branch.name,
                        business_name=candidate.name, industry_name=candidate.industry_name,
                        distance_km=candidate.distance_km, facts=[fact.fact for fact in reason_facts],
                    ),
                    reason_summary=reason_facts[0].summary,
                )
            )

    result.stats = {
        "candidates": len(candidates),
        "excluded": excluded,
        "passed": len(passed),
        "scoring_events": len(events),
        "recommendations": len(ranked),
        "exploration_slots": sum(1 for item in ranked if item.is_exploration_slot),
    }
    return result


# ─────────────────────────── 브리프 ───────────────────────────


def generate_briefs(jobs: list[BriefJob], llm: LlmClient | None, config: PipelineConfig) -> list[BriefContent]:
    def run_job(job: BriefJob) -> BriefContent:
        try:
            return generate_brief(
                job.brief_input,
                reason_summary=job.reason_summary,
                llm=llm,
                config=config.briefing,
            )
        except Exception:  # noqa: BLE001 — job 하나의 비결정적 생성 실패를 다른 브리프와 격리한다.
            logger.exception(
                "브리프 생성 실패 — 정형 화법 재시도: recommendation_id=%s",
                job.brief_input.recommendation_id,
            )
            # 결정론적 TEMPLATE 생성까지 실패하면 예외를 전파해 기존 전체 실패 처리를 따른다.
            fallback = generate_brief(
                job.brief_input,
                reason_summary=job.reason_summary,
                llm=None,
                config=config.briefing,
            )
            return fallback.model_copy(
                update={
                    "validation_errors": [
                        *fallback.validation_errors,
                        "브리프 생성 예외 — 정형 화법으로 대체",
                    ]
                }
            )

    if llm is None or len(jobs) <= 1:
        return [run_job(job) for job in jobs]
    with ThreadPoolExecutor(max_workers=max(1, get_settings().llm_max_concurrency)) as executor:
        return list(executor.map(run_job, jobs))


# ─────────────────────────── 오케스트레이션 ───────────────────────────


def _params_snapshot(
    target_date: date,
    thresholds: dict[str, repo.ThresholdParam],
    weights: list[Any],
    llm: LlmClient | None,
) -> dict[str, Any]:
    """PRIN-08: 이 실행의 입력(임계치·가중치·설정 버전)을 기록해 같은 입력으로 재생산할 수 있게 한다."""
    return {
        "target_date": target_date.isoformat(),
        "thresholds": {
            key: {"value": value.threshold_value, "unit": value.unit, "updated_at": value.updated_at.isoformat()}
            for key, value in sorted(thresholds.items())
        },
        "signal_weights": [weight.model_dump() for weight in weights],
        "pipeline_config_sha256": hashlib.sha256(PIPELINE_CONFIG_PATH.read_bytes()).hexdigest(),
        "prompt_version": PROMPT_VERSION,
        "llm_model": llm.model if llm else None,
    }


def run_pipeline(target_date: date, run_id: int | None) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[str]]:
    """(stage_stats, source_status, params_snapshot, 실패 지점코드 목록)"""
    config = get_pipeline_config()
    settings = get_settings()
    reference_ts = datetime.combine(target_date, SLA_TIME, KST)
    stats: dict[str, Any] = {}
    stage_started = time.monotonic()

    with get_connection() as conn:
        thresholds = repo.load_thresholds(conn)
        weight_entries = repo.load_signal_weights(conn)
        branches_all = repo.load_effective_branches(conn, reference_ts)
    missing_params = {"EVENT_COOLDOWN_DAYS", "DAILY_EVENT_CAP", "CONTACT_COOLDOWN_DAYS"} - thresholds.keys()
    if missing_params:
        raise RuntimeError(f"THRESHOLD_CONFIG 초기값 누락: {', '.join(sorted(missing_params))} (seed.sql 확인)")

    llm = create_llm_client(settings)
    params = _params_snapshot(target_date, thresholds, weight_entries, llm)
    weights = WeightTable(weight_entries, default_weight=config.scoring.default_weight,
                          min_sample=config.recommendation.min_sample_for_update)
    branches = [branch for branch in branches_all if branch.has_coordinates]
    stats["branches"] = {
        "effective": len(branches_all),
        "with_coordinates": len(branches),
        "without_coordinates": [b.branch_code for b in branches_all if not b.has_coordinates],
        "using_history": [b.branch_code for b in branches_all if b.from_history],
    }
    area = AreaIndex(branches)

    # 1) connectors
    outcomes = collect_all_sources(branches, target_date, config)
    stats["collect_s"] = round(time.monotonic() - stage_started, 2)

    # 2) 사업자 상태 검증: 인허가 1차 → 국세청 2차(덮어씀)
    stage_started = time.monotonic()
    openings, permit_stats = apply_permit_changes(outcomes["PERMIT_DAILY"], area, config)
    nts_outcome, nts_missing = collect_nts(branches, target_date, config)
    outcomes["NTS_STATUS"] = nts_outcome
    stats["status_verification"] = {
        "permit": permit_stats,
        "nts": apply_nts_results(nts_outcome, target_date),
        "nts_skipped_without_biz_reg_no": nts_missing,
        "elapsed_s": round(time.monotonic() - stage_started, 2),
    }

    # 3) 정규화 + 이벤트 승격, 4) 명부
    failed: list[str] = []
    sensing_stats: dict[str, Any] = {}
    targeting_stats: dict[str, Any] = {}
    brief_jobs: list[BriefJob] = []
    for branch in branches:
        try:
            drafts = normalize_for_branch(branch, outcomes, openings, config)
            sensing_stats[branch.branch_code] = sense_branch(branch, drafts, target_date, thresholds, weights, run_id)
            targeting = target_branch(branch, target_date, thresholds, weights, config, run_id)
            targeting_stats[branch.branch_code] = targeting.stats
            brief_jobs.extend(targeting.brief_jobs)
        except Exception:  # noqa: BLE001 — 지점 1곳 실패가 다른 지점을 막지 않는다
            logger.exception("지점 처리 실패: %s", branch.branch_code)
            failed.append(branch.branch_code)
    stats["sensing"] = sensing_stats
    stats["targeting"] = targeting_stats

    # 5) 브리프
    stage_started = time.monotonic()
    briefs = generate_briefs(brief_jobs, llm, config)
    with get_connection() as conn:
        for brief in briefs:
            repo.insert_brief(conn, brief)
    status_counts: dict[str, int] = {}
    for brief in briefs:
        status_counts[brief.generation_status] = status_counts.get(brief.generation_status, 0) + 1
    stats["briefing"] = {"generated": len(briefs), "by_status": status_counts,
                         "llm_configured": llm is not None, "elapsed_s": round(time.monotonic() - stage_started, 2)}

    return stats, [outcome.to_status() for outcome in outcomes.values()], params, failed


def run(target_date: date | None, run_id: int | None) -> int:
    setup_logging("daily")
    settings = get_settings()

    with get_connection() as conn:
        if run_id is None:
            stale = repo.fail_stale_runs(conn, settings.batch_stale_minutes)
            if stale:
                log_fields(logger, logging.WARNING, "장기 RUNNING 실행을 실패 처리", count=stale)
            target_date = target_date or today_kst()
            run_id = repo.create_scheduled_run(conn, target_date)
            if run_id is None:
                log_fields(logger, logging.WARNING, "이미 실행 중인 배치가 있어 종료합니다(CONST-17)")
                return 0
            run_row = repo.get_run(conn, run_id)
        else:
            run_row = repo.get_run(conn, run_id)
            if run_row is None or run_row["status"] != "RUNNING":
                log_fields(logger, logging.ERROR, "실행할 BATCH_RUN이 없거나 RUNNING 상태가 아닙니다", run_id=run_id)
                return 1
            target_date = run_row["target_date"]
            repo.mark_run_started(conn, run_id)
    assert run_row is not None and target_date is not None

    started = time.monotonic()
    log_fields(logger, logging.INFO, "일간 배치 시작", run_id=run_id, run_type=run_row["run_type"],
               target_date=target_date.isoformat())
    status, failure_reason = "SUCCESS", None
    stats: dict[str, Any] = {}
    source_status: list[dict[str, Any]] = []
    params: dict[str, Any] = {}
    try:
        stats, source_status, params, failed = run_pipeline(target_date, run_id)
        if failed:
            status, failure_reason = "FAILED", f"지점 처리 실패: {', '.join(failed)}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("일간 배치 실패")
        status, failure_reason = "FAILED", f"{type(exc).__name__}: {exc}"[:500]
    stats["total_s"] = round(time.monotonic() - started, 2)

    with get_connection() as conn:
        repo.finish_run(conn, run_id, status=status, failure_reason=failure_reason, params_snapshot=params,
                        stage_stats=stats, source_status=source_status)
        # REQ-15 / RULE-SENSE-06: 요청·결과를 감사 로그에 남긴다.
        repo.insert_audit(conn, actor_user_id=run_row["triggered_by"], action="BATCH_RUN_COMPLETED",
                          entity_type="batch_run", entity_id=str(run_id),
                          after_value={"status": status, "failure_reason": failure_reason,
                                       "run_type": run_row["run_type"], "target_date": target_date.isoformat()})

    finished_at = datetime.now(KST)
    sla_deadline = datetime.combine(target_date, SLA_TIME, KST)
    if run_row["run_type"] == "SCHEDULED" and finished_at > sla_deadline:
        log_fields(logger, logging.ERROR, "SLA_MISSED: 07:30 이후 완료", run_id=run_id,
                   finished_at=finished_at.isoformat())
    log_fields(logger, logging.INFO if status == "SUCCESS" else logging.ERROR, "일간 배치 종료",
               run_id=run_id, status=status, failure_reason=failure_reason, total_s=stats["total_s"])
    return 0 if status == "SUCCESS" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="C-MAKER 일간 배치")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="명부 기준일(기본: 오늘, KST)")
    parser.add_argument("--run-id", type=int, default=None, help="API가 생성한 수동 재실행 BATCH_RUN ID")
    args = parser.parse_args(argv)
    try:
        return run(args.date, args.run_id)
    finally:
        close_pool()


if __name__ == "__main__":
    sys.exit(main())
