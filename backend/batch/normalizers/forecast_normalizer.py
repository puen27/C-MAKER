"""기상청 단기·중기예보 → 예보 SIGNAL 정규화 + 브리프 '날씨 참고' 문장 (순수 함수).

이벤트 후보(scope=INDUSTRY, 업종 적합도로 적용 — 환율·유가와 같은 '업종 영향' 신호):
- TEMP_SHIFT_FORECAST   기온 급변: 내일·모레 최저/최고기온이 오늘과 차이 나는 정도(°C)
- SEASON_SHIFT_FORECAST 계절 전환: 5일 이후(중기) 평균 최저기온 − 오늘~3일 뒤(단기) 평균 최저기온(°C)
- FIRST_FREEZE_FORECAST 첫 영하: 시즌(9월~2월) 첫 최저기온 영하 예보. 이미 이 시즌에 이벤트가 있으면 raw=0
- FIRST_HEAT_FORECAST   첫 폭염: 시즌(5~9월) 첫 최고기온 33°C 이상 예보. 위와 같은 방식

모든 예보 신호는 detail.valid_until(예보 대상일)을 갖는다. 그 날짜가 지나면 스코어링에서 빠진다
(scorer.is_expired) — 예보 날짜까지만 사유로 쓰고, 그 사이 예보가 약해져도 유지한다.

비·눈 예보는 이벤트가 아니다. weather_note()가 브리프 참고 문장만 만든다(순위·근거·화법 미사용).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from backend.batch.connectors.kma_forecast_connector import grid_key
from backend.common.config import ForecastConfig, PipelineConfig
from backend.common.geo import extract_sido, kma_grid
from backend.common.schemas.branch import BranchContext
from backend.common.schemas.signal import SignalDraft

SOURCE = "KMA_FORECAST"
FORECAST_SIGNAL_TYPES = (
    "TEMP_SHIFT_FORECAST",
    "SEASON_SHIFT_FORECAST",
    "FIRST_FREEZE_FORECAST",
    "FIRST_HEAT_FORECAST",
)
_SNOW_PTY = {"2", "3", "6", "7"}  # 비/눈, 눈, (초단기) 빗방울눈날림, 눈날림


@dataclass(frozen=True)
class DayTemp:
    day: date
    tmn: float | None
    tmx: float | None
    origin: str  # "단기" | "중기"


def _clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _parse_ymd(value: str) -> date | None:
    try:
        return datetime.strptime(str(value), "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def month_day(day: date) -> str:
    return f"{day.month}월 {day.day}일"


def issued_label(ymd: str, hhmm: str) -> str:
    day = _parse_ymd(ymd)
    if day is None:
        return "최근 발표"
    return f"{month_day(day)} {int(str(hhmm)[:2]):02d}시 발표"


def branch_grid(branch: BranchContext) -> tuple[int, int] | None:
    if not branch.has_coordinates:
        return None
    return kma_grid(branch.lat, branch.lng)  # type: ignore[arg-type]


def _short_items(branch: BranchContext, payload: dict[str, Any]) -> list[dict[str, Any]]:
    grid = branch_grid(branch)
    if grid is None:
        return []
    return ((payload.get("short") or {}).get("grids") or {}).get(grid_key(*grid), [])


def daily_temperatures(branch: BranchContext, payload: dict[str, Any], config: PipelineConfig) -> dict[date, DayTemp]:
    """단기(격자) 일 최저·최고 + 중기(시·도) N일 뒤 최저·최고. 같은 날짜는 단기를 우선한다."""
    series: dict[date, DayTemp] = {}
    short_min: dict[date, float] = {}
    short_max: dict[date, float] = {}
    for item in _short_items(branch, payload):
        day = _parse_ymd(item.get("fcstDate"))
        value = _float(item.get("fcstValue"))
        if day is None or value is None:
            continue
        if item.get("category") == "TMN":
            short_min[day] = value
        elif item.get("category") == "TMX":
            short_max[day] = value
    for day in sorted(set(short_min) | set(short_max)):
        series[day] = DayTemp(day, short_min.get(day), short_max.get(day), "단기")

    sido = extract_sido(branch.address) or ""
    reg_id = config.kma_mid_ta_region_by_sido.get(sido)
    mid = payload.get("mid") or {}
    item = (mid.get("ta") or {}).get(reg_id or "")
    issued = _parse_ymd(str(mid.get("tm_fc") or "")[:8])
    if item and issued:
        for offset in range(3, 11):
            day = issued + timedelta(days=offset)
            if day in series:
                continue
            tmn, tmx = _float(item.get(f"taMin{offset}")), _float(item.get(f"taMax{offset}"))
            if tmn is None and tmx is None:
                continue
            series[day] = DayTemp(day, tmn, tmx, "중기")
    return series


def _issued_texts(payload: dict[str, Any]) -> tuple[str, str]:
    short = payload.get("short") or {}
    mid = payload.get("mid") or {}
    tm_fc = str(mid.get("tm_fc") or "")
    return (
        issued_label(str(short.get("base_date") or ""), str(short.get("base_time") or "0200")),
        issued_label(tm_fc[:8], tm_fc[8:12] or "1800"),
    )


def season_label(signal_type: str, day: date, config: ForecastConfig) -> str | None:
    """시즌 식별자. 시즌 밖이면 None(신호를 만들지 않는다)."""
    if signal_type == "FIRST_FREEZE_FORECAST":
        start = config.freeze_season_start_month
        if day.month >= start:
            return f"{day.year}-{day.year + 1}"
        if day.month <= 2:
            return f"{day.year - 1}-{day.year}"
        return None
    if signal_type == "FIRST_HEAT_FORECAST":
        return str(day.year) if day.month in config.heat_season_months else None
    return None


def season_start(signal_type: str, day: date, config: ForecastConfig) -> date | None:
    label = season_label(signal_type, day, config)
    if label is None:
        return None
    if signal_type == "FIRST_FREEZE_FORECAST":
        return date(int(label[:4]), config.freeze_season_start_month, 1)
    return date(int(label), min(config.heat_season_months), 1)


def _draft(branch: BranchContext, snapshot_id: int, as_of: date, signal_type: str, target_key: str,
           intensity: float, raw: float, unit: str, detail: dict[str, Any]) -> SignalDraft:
    return SignalDraft(
        snapshot_id=snapshot_id,
        source_name=SOURCE,
        branch_id=branch.id,
        signal_type=signal_type,
        scope="INDUSTRY",
        target_key=target_key,
        intensity=round(_clip01(intensity), 3),
        raw_value=raw,
        unit=unit,
        as_of_date=as_of,
        detail=detail,
    )


def normalize_forecast(
    branch: BranchContext,
    payload: dict[str, Any],
    *,
    snapshot_id: int,
    as_of_date: date,
    target_date: date,
    config: PipelineConfig,
    seen_this_season: set[str] | None = None,
) -> list[SignalDraft]:
    """한 지점의 예보 신호. seen_this_season: 이 시즌에 이미 승격된 '첫 영하/첫 폭염' 신호종류."""
    fc = config.forecast
    seen = seen_this_season or set()
    series = daily_temperatures(branch, payload, config)
    if not series:
        return []
    short_issued, mid_issued = _issued_texts(payload)
    signals: list[SignalDraft] = []
    today = series.get(target_date)

    # ① 기온 급변 — 내일·모레 중 오늘과 차이가 가장 큰 값(최저 또는 최고)
    if today is not None:
        best: tuple[float, date, str, float, float] | None = None
        for offset in fc.shift_days:
            day = target_date + timedelta(days=offset)
            target = series.get(day)
            if target is None or target.origin != "단기":
                continue
            for kind, now_value, then_value in (("최저", today.tmn, target.tmn), ("최고", today.tmx, target.tmx)):
                if now_value is None or then_value is None:
                    continue
                diff = then_value - now_value
                if best is None or abs(diff) > abs(best[0]):
                    best = (diff, day, kind, now_value, then_value)
        if best is not None:
            diff, day, kind, now_value, then_value = best
            signals.append(_draft(
                branch, snapshot_id, as_of_date, "TEMP_SHIFT_FORECAST", "FORECAST:TEMP_SHIFT",
                abs(diff) / fc.temp_shift_saturation_c, round(abs(diff), 1), "°C",
                {"forecast_date": day.isoformat(), "kind": kind, "today_value": now_value,
                 "forecast_value": then_value, "diff": round(diff, 1), "issued": short_issued,
                 "valid_until": day.isoformat()},
            ))

    # ② 계절 전환 — 단기 구간(오늘~3일 뒤) 평균 최저 vs 중기 구간 평균 최저
    near = [series[d].tmn for d in sorted(series) if series[d].origin == "단기" and d >= target_date
            and series[d].tmn is not None]
    far_days = [d for d in sorted(series) if series[d].origin == "중기" and series[d].tmn is not None]
    if len(near) >= 2 and len(far_days) >= 3:
        near_days = [d for d in sorted(series) if series[d].origin == "단기" and d >= target_date
                     and series[d].tmn is not None]
        near_mean = sum(near) / len(near)  # type: ignore[arg-type]
        far_mean = sum(series[d].tmn for d in far_days) / len(far_days)  # type: ignore[misc]
        diff = round(far_mean - near_mean, 1)
        signals.append(_draft(
            branch, snapshot_id, as_of_date, "SEASON_SHIFT_FORECAST", "FORECAST:SEASON_SHIFT",
            abs(diff) / fc.season_shift_saturation_c, abs(diff), "°C",
            {"near_start": near_days[0].isoformat(), "near_end": near_days[-1].isoformat(),
             "near_mean": round(near_mean, 1), "far_start": far_days[0].isoformat(),
             "far_end": far_days[-1].isoformat(), "far_mean": round(far_mean, 1), "diff": diff,
             "issued": short_issued, "issued_mid": mid_issued, "valid_until": far_days[0].isoformat()},
        ))

    # ③④ 첫 영하 / 첫 폭염 — 시즌 첫 발생만 승격(raw=1), 이미 있었으면 raw=0으로 원장에만 남긴다
    future = [series[d] for d in sorted(series) if d > target_date]
    for signal_type, pick, unit_value in (
        ("FIRST_FREEZE_FORECAST", lambda t: t.tmn is not None and t.tmn < fc.freeze_tmin_c, "tmn"),
        ("FIRST_HEAT_FORECAST", lambda t: t.tmx is not None and t.tmx >= fc.heat_tmax_c, "tmx"),
    ):
        label = season_label(signal_type, target_date, fc)
        if label is None:
            continue
        hit = next((t for t in future if pick(t)), None)
        if hit is None:
            continue
        already = signal_type in seen
        value = getattr(hit, unit_value)
        signals.append(_draft(
            branch, snapshot_id, as_of_date, signal_type,
            f"FORECAST:{'FREEZE' if signal_type == 'FIRST_FREEZE_FORECAST' else 'HEAT'}:{label}",
            0.0 if already else fc.first_event_intensity, 0 if already else 1, "건",
            {"forecast_date": hit.day.isoformat(), "value": value, "origin": hit.origin,
             "issued": short_issued if hit.origin == "단기" else mid_issued, "season": label,
             "already_this_season": already, "valid_until": hit.day.isoformat()},
        ))
    return signals


def weather_note(
    branch: BranchContext, payload: dict[str, Any], *, target_date: date, config: ForecastConfig
) -> str | None:
    """1~2일 뒤 강수확률이 기준 이상이거나 눈 예보면 브리프 참고 문장. 업종 필터는 호출 측이 한다."""
    pop: dict[date, int] = {}
    snow: dict[date, bool] = {}
    for item in _short_items(branch, payload):
        day = _parse_ymd(item.get("fcstDate"))
        if day is None:
            continue
        category, value = item.get("category"), str(item.get("fcstValue") or "").strip()
        if category == "POP":
            number = _float(value)
            if number is not None:
                pop[day] = max(pop.get(day, 0), int(number))
        elif category == "SNO" and value not in ("", "적설없음", "0", "0.0"):
            snow[day] = True
        elif category == "PTY" and value in _SNOW_PTY:
            snow[day] = True

    parts: list[str] = []
    any_snow = False
    for offset in config.weather_note_days:
        day = target_date + timedelta(days=offset)
        is_snow = snow.get(day, False)
        if pop.get(day, 0) >= config.rain_pop_pct or is_snow:
            parts.append(f"{month_day(day)}(강수확률 {pop.get(day, 0)}%)")
            any_snow = any_snow or is_snow
    if not parts:
        return None
    short_issued, _mid = _issued_texts(payload)
    kind = "눈" if any_snow else "비"
    return f"{'·'.join(parts)} {kind} 예보가 있습니다(기상청 단기예보 {short_issued})."


def needs_weather_note(industry_name: str | None, config: ForecastConfig) -> bool:
    name = industry_name or ""
    return any(keyword and keyword in name for keyword in config.weather_note_keywords)
