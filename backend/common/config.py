"""환경변수(.env) 및 파이프라인 설정(pipeline.toml) 로더.

- OPS-01 / K-3: 인증키·접속정보는 저장소 루트 `.env`에서만 읽고 코드에 하드코딩하지 않는다.
- CLAUDE.md §2: 배치 판정에 쓰는 구조적 설정(업종×신호 적합도, 소스 매핑 등)은
  `backend/config/pipeline.toml`로 외부화한다. 본부가 UI에서 조정하는 신호 임계치·운영 파라미터는
  DB의 THRESHOLD_CONFIG에 있다(REQ-14).
"""

from __future__ import annotations

import tomllib
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
PIPELINE_CONFIG_PATH = BACKEND_ROOT / "config" / "pipeline.toml"

# 모든 업무 날짜(명부 기준일, 07:30 SLA, 익일 반영)는 한국 시간 기준이다.
KST = ZoneInfo("Asia/Seoul")


def now_kst() -> datetime:
    return datetime.now(KST)


def today_kst() -> date:
    return now_kst().date()


class Settings(BaseSettings):
    """저장소 루트 `.env`에서 읽는 실행 환경 설정 (docs/10-implementation-guide.md §3)."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── DB ──
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "myapp_db"
    db_user: str = ""
    db_password: str = ""
    # 공유 DB(myapp_db)의 기존 테이블과 이름이 충돌하지 않도록 전용 스키마를 쓴다.
    db_schema: str = "cmaker"
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10

    # ── JWT ──
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # ── 공공데이터 API ──
    data_go_kr_service_key: str = ""
    ecos_api_key: str = ""
    opinet_api_key: str = ""
    # 지점 주소 지오코딩(RULE-BRANCH-03) — 공간정보 오픈플랫폼(VWorld) 인증키
    vworld_api_key: str = ""
    # 지방행정 인허가 전수 파일(CSV)을 내려받아 두는 디렉터리 (REQ-16, F-2)
    permit_full_data_dir: str = ""
    # 파일형 원본(인허가 전수 등)을 날짜 파티션으로 보관하는 디렉터리 (재현성, OPS-05)
    snapshot_archive_dir: str = str(REPO_ROOT / "data" / "snapshots")
    external_http_timeout_seconds: float = 15.0

    # ── LLM (LiteLLM Gateway, OpenAI-Compatible) ──
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = "claude-opus-5"
    # 게이트웨이 호출 타임아웃(초).
    # EC2 실측(2026-09-30, claude-opus-5, thinking 비활성, generate_brief 5건):
    #   min 3.24초 / median 3.77초 / max 4.61초 → UC-07 "브리프 1건 5초 이내" 충족.
    # 개발 PC에서는 같은 호출이 7.4초였다. 게이트웨이가 EC2와 같은 리전에 있어 서버에서만 빠르다.
    # max_output_tokens=400 상한을 감안해 실측 max의 약 2배로 여유를 둔다.
    llm_timeout_seconds: float = 10.0
    llm_max_concurrency: int = 4
    # claude-opus-5 / claude-opus-4-8은 extended thinking이 기본 ON이고, thinking 토큰이
    # max_tokens를 먼저 소진해 content가 빈 문자열로 돌아온다(게이트웨이 실측).
    # 브리프는 추론이 아니라 확정된 사실의 문장화이므로 기본 비활성으로 둔다.
    llm_disable_thinking: bool = True

    # ── 배치 ──
    # VAL-12 수동 재실행 쿨다운(분). 코드 상수로 두지 않는다.
    batch_cooldown_minutes: int = 30
    # RUNNING 상태로 이 시간(분) 이상 남은 실행은 비정상 종료로 보고 FAILED 처리한다.
    batch_stale_minutes: int = 180
    log_dir: str = ""

    # ── 서버 ──
    frontend_origin: str = "http://localhost"
    app_env: str = "prod"

    @property
    def is_dev(self) -> bool:
        return self.app_env.lower() == "dev"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# ─────────────────────────── pipeline.toml ───────────────────────────


class RecommendationConfig(BaseModel):
    top_n: int = 20
    exploration_slots: int = 3
    # CLAUDE.md §9: 탐색 슬롯 가동은 Phase 2. MVP는 구조만 두고 기본 비활성.
    exploration_enabled: bool = False
    min_sample_for_update: int = 30


class ScoringConfig(BaseModel):
    proximity_min: float = 0.5
    industry_fit_match: float = 1.2
    industry_fit_default: float = 1.0
    default_weight: float = 1.0
    event_lookback_days: int = 7


class NormalizationConfig(BaseModel):
    area_openings_saturation: float = 10
    industry_openings_saturation: float = 5
    fx_change_saturation_pct: float = 3.0
    oil_change_saturation_pct: float = 3.0
    warning_intensity_advisory: float = 0.6
    warning_intensity_alert: float = 1.0
    new_opening_max_age_days: int = 90


class FreshnessConfig(BaseModel):
    weight_license: float = 1 / 3
    weight_no_contact: float = 1 / 3
    weight_signal_fit: float = 1 / 3
    license_decay_days: float = 180
    no_contact_saturation_days: float = 30


class ExclusionConfig(BaseModel):
    # 부적합 사유별 배제 기간(일). 0이면 영구 배제.
    reject_exclusion_days: dict[str, int] = Field(default_factory=dict)


class BriefingConfig(BaseModel):
    max_script_sentences: int = 3
    forbidden_expressions: list[str] = Field(default_factory=list)
    product_terms: list[str] = Field(default_factory=list)
    default_checklist: list[str] = Field(default_factory=list)
    greeting_org_name: str = "○○은행"
    max_output_tokens: int = 400


class SourceConfig(BaseModel):
    """소스별 엔드포인트·표시명·수집 파라미터. 스펙 변경 시 코드 대신 이 설정을 고친다."""

    display_name: str
    url: str = ""
    expected_lag_days: int = 0
    options: dict[str, Any] = Field(default_factory=dict)


class PipelineConfig(BaseModel):
    recommendation: RecommendationConfig
    scoring: ScoringConfig
    normalization: NormalizationConfig
    freshness: FreshnessConfig
    exclusion: ExclusionConfig
    briefing: BriefingConfig
    sources: dict[str, SourceConfig]
    industry_signal_fit: dict[str, dict[str, float]]
    kma_station_by_sido: dict[str, int]
    opinet_sido_code: dict[str, str]

    def source_display_name(self, source_name: str) -> str:
        source = self.sources.get(source_name)
        return source.display_name if source else source_name

    def signal_fit(self, signal_type: str, industry_name: str | None) -> float:
        """업종×신호 적합도(0~1). RULE-TARGET-05 ③ 및 업종 단위 거시 신호 적용 여부에 쓴다."""
        mapping = self.industry_signal_fit.get(signal_type, {})
        best = 0.0
        name = industry_name or ""
        for keyword, fit in mapping.items():
            if keyword == "*":
                best = max(best, fit)
            elif keyword and keyword in name:
                best = max(best, fit)
        return best


@lru_cache(maxsize=1)
def get_pipeline_config() -> PipelineConfig:
    with PIPELINE_CONFIG_PATH.open("rb") as file:
        raw = tomllib.load(file)
    return PipelineConfig.model_validate(raw)
