"""기상청 예보 신호(기온 급변·계절 전환·첫 영하·첫 폭염), 날씨 참고, 예보 유효기간, 신호별 명부 상한."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.batch.briefing.brief_generator import generate_brief
from backend.batch.briefing.citation_guard import validate_script
from backend.batch.briefing.fact_builder import _event_fact
from backend.batch.normalizers.forecast_normalizer import (
    needs_weather_note,
    normalize_forecast,
    season_label,
    season_start,
    weather_note,
)
from backend.batch.sensing.threshold_engine import exceeds_threshold
from backend.batch.targeting.exploration import apply_signal_share_cap
from backend.batch.targeting.scorer import is_expired
from backend.common.config import get_pipeline_config
from backend.common.geo import kma_grid
from backend.common.schemas.brief import BriefInput
from backend.common.schemas.recommendation import ScoredCandidate, SignalContribution
from backend.tests.factories import active_event, branch, fact

CONFIG = get_pipeline_config()
TARGET = date(2026, 10, 13)
BRANCH = branch()  # 서울 강남, (37.5, 127.036)
GRID = kma_grid(BRANCH.lat, BRANCH.lng)  # type: ignore[arg-type]
THRESHOLDS = {"TEMP_SHIFT_FORECAST": 5.0, "SEASON_SHIFT_FORECAST": 4.0,
              "FIRST_FREEZE_FORECAST": 0.0, "FIRST_HEAT_FORECAST": 0.0}


def _ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


def _payload(temps: dict[int, tuple[float, float]], *, mid: dict[int, tuple[float, float]] | None = None,
             pops: dict[int, int] | None = None, snow_day: int | None = None, target: date = TARGET) -> dict:
    """temps: {오늘부터 n일 뒤: (최저, 최고)} 단기, mid: {전날 18시 발표 기준 N일 뒤: (최저, 최고)}"""
    items = []
    for offset, (tmn, tmx) in temps.items():
        day = _ymd(target + timedelta(days=offset))
        items += [{"category": "TMN", "fcstDate": day, "fcstTime": "0600", "fcstValue": str(tmn)},
                  {"category": "TMX", "fcstDate": day, "fcstTime": "1500", "fcstValue": str(tmx)}]
    for offset, pop in (pops or {}).items():
        items.append({"category": "POP", "fcstDate": _ymd(target + timedelta(days=offset)), "fcstTime": "1200",
                      "fcstValue": str(pop)})
    if snow_day is not None:
        items.append({"category": "SNO", "fcstDate": _ymd(target + timedelta(days=snow_day)), "fcstTime": "0900",
                      "fcstValue": "1cm 미만"})
    ta = {}
    for offset, (tmn, tmx) in (mid or {}).items():
        ta[f"taMin{offset}"], ta[f"taMax{offset}"] = tmn, tmx
    return {
        "target_date": target.isoformat(),
        "short": {"base_date": _ymd(target), "base_time": "0200", "grids": {f"{GRID[0]},{GRID[1]}": items}},
        "mid": {"tm_fc": _ymd(target - timedelta(days=1)) + "1800",
                "ta": {"11B10101": {"regId": "11B10101", **ta}} if ta else {}, "land": {}, "error": None},
    }


def _signals(payload: dict, *, seen: set[str] | None = None, target: date = TARGET) -> dict[str, object]:
    drafts = normalize_forecast(BRANCH, payload, snapshot_id=1, as_of_date=target, target_date=target,
                                config=CONFIG, seen_this_season=seen)
    return {d.signal_type: d for d in drafts}


# ─────────────────────────── 격자 변환 ───────────────────────────


@pytest.mark.parametrize(("lat", "lng", "expected"), [
    (37.5657651, 126.9676375, (60, 127)),   # 서울 중구
    (37.579871, 126.977041, (60, 127)),     # 서울 종로구(기상청 활용가이드 예시)
    (33.4996213, 126.5311884, (53, 38)),    # 제주시
])
def test_kma_grid_matches_official_points(lat, lng, expected):
    assert kma_grid(lat, lng) == expected


# ─────────────────────────── 기온 급변 ───────────────────────────


def test_temp_shift_picks_largest_change_within_two_days():
    signals = _signals(_payload({0: (12, 21), 1: (6, 18), 2: (9, 20), 3: (2, 15)}))
    shift = signals["TEMP_SHIFT_FORECAST"]
    assert shift.raw_value == 6.0                         # 내일 최저 12 → 6 (3일 뒤 2℃는 비교 대상 아님)
    assert shift.scope == "INDUSTRY" and shift.unit == "°C"
    assert shift.detail["kind"] == "최저" and shift.detail["diff"] == -6.0
    assert shift.detail["valid_until"] == "2026-10-14"
    assert exceeds_threshold(shift, THRESHOLDS)[0]


def test_temp_shift_below_threshold_is_stored_but_not_promoted():
    shift = _signals(_payload({0: (12, 21), 1: (10, 20), 2: (11, 22)}))["TEMP_SHIFT_FORECAST"]
    assert shift.raw_value == 2.0
    assert not exceeds_threshold(shift, THRESHOLDS)[0]


def test_temp_shift_needs_today_values():
    assert "TEMP_SHIFT_FORECAST" not in _signals(_payload({1: (6, 18), 2: (9, 20)}))


# ─────────────────────────── 계절 전환 ───────────────────────────


def test_season_shift_compares_mid_range_with_short_range():
    payload = _payload({0: (14, 22), 1: (13, 21), 2: (12, 21), 3: (11, 20)},
                       mid={5: (8, 17), 6: (7, 16), 7: (6, 15), 8: (5, 14)})
    season = _signals(payload)["SEASON_SHIFT_FORECAST"]
    assert season.detail["near_mean"] == 12.5 and season.detail["far_mean"] == 6.5
    assert season.raw_value == 6.0 and season.detail["diff"] == -6.0
    # 중기 키 N은 발표일(전날) 기준 N일 뒤 → taMin5는 오늘+4일
    assert season.detail["far_start"] == "2026-10-17"
    assert season.detail["valid_until"] == "2026-10-17"
    assert exceeds_threshold(season, THRESHOLDS)[0]


def test_season_shift_skipped_without_mid_forecast():
    assert "SEASON_SHIFT_FORECAST" not in _signals(_payload({0: (14, 22), 1: (13, 21), 2: (12, 21)}))


# ─────────────────────────── 첫 영하 / 첫 폭염 ───────────────────────────


def test_first_freeze_promotes_once_per_season():
    payload = _payload({0: (3, 12), 1: (1, 10), 2: (-1.5, 8)})
    freeze = _signals(payload)["FIRST_FREEZE_FORECAST"]
    assert freeze.raw_value == 1 and freeze.detail["value"] == -1.5
    assert freeze.detail["forecast_date"] == "2026-10-15" and freeze.detail["season"] == "2026-2027"
    assert freeze.target_key == "FORECAST:FREEZE:2026-2027"
    assert exceeds_threshold(freeze, THRESHOLDS)[0]

    again = _signals(payload, seen={"FIRST_FREEZE_FORECAST"})["FIRST_FREEZE_FORECAST"]
    assert again.raw_value == 0 and again.intensity == 0
    assert not exceeds_threshold(again, THRESHOLDS)[0]


def test_first_freeze_uses_mid_forecast_and_ignores_today():
    payload = _payload({0: (-2, 5), 1: (2, 9)}, mid={6: (-3, 4)})
    freeze = _signals(payload)["FIRST_FREEZE_FORECAST"]
    assert freeze.detail["origin"] == "중기" and freeze.detail["forecast_date"] == "2026-10-18"


def test_first_heat_only_in_heat_season():
    hot = {0: (24, 31), 1: (25, 34)}
    assert "FIRST_HEAT_FORECAST" not in _signals(_payload(hot))           # 10월은 폭염 시즌 아님
    july = date(2026, 7, 2)
    heat = _signals(_payload(hot, target=july), target=july)["FIRST_HEAT_FORECAST"]
    assert heat.raw_value == 1 and heat.detail["value"] == 34


@pytest.mark.parametrize(("day", "freeze", "heat"), [
    (date(2026, 10, 13), "2026-2027", None),
    (date(2027, 1, 20), "2026-2027", None),
    (date(2026, 4, 1), None, None),
    (date(2026, 8, 1), None, "2026"),
])
def test_season_labels(day, freeze, heat):
    fc = CONFIG.forecast
    assert season_label("FIRST_FREEZE_FORECAST", day, fc) == freeze
    assert season_label("FIRST_HEAT_FORECAST", day, fc) == heat


def test_season_start_dates():
    fc = CONFIG.forecast
    assert season_start("FIRST_FREEZE_FORECAST", date(2027, 1, 20), fc) == date(2026, 9, 1)
    assert season_start("FIRST_HEAT_FORECAST", date(2026, 8, 1), fc) == date(2026, 5, 1)


# ─────────────────────────── 유효기간 ───────────────────────────


def test_forecast_event_expires_after_forecast_date():
    event = active_event(1, signal_type="TEMP_SHIFT_FORECAST", detail={"valid_until": "2026-10-14"})
    assert not is_expired(event, date(2026, 10, 14))
    assert is_expired(event, date(2026, 10, 15))
    assert not is_expired(active_event(2), date(2030, 1, 1))  # 예보가 아닌 이벤트는 해당 없음


# ─────────────────────────── 날씨 참고 ───────────────────────────


def test_weather_note_for_rain_and_snow():
    note = weather_note(BRANCH, _payload({0: (5, 10)}, pops={1: 80, 2: 30}), target_date=TARGET,
                        config=CONFIG.forecast)
    assert note == "10월 14일(강수확률 80%) 비 예보가 있습니다(기상청 단기예보 10월 13일 02시 발표)."
    snow = weather_note(BRANCH, _payload({0: (0, 3)}, pops={2: 40}, snow_day=2), target_date=TARGET,
                        config=CONFIG.forecast)
    assert snow is not None and "눈 예보" in snow
    assert weather_note(BRANCH, _payload({0: (5, 10)}, pops={1: 60}), target_date=TARGET,
                        config=CONFIG.forecast) is None


def test_weather_note_only_for_weather_sensitive_industries():
    assert needs_weather_note("음식·비알코올·카페", CONFIG.forecast)
    assert needs_weather_note("수리·개인·자동차 수리·세차·자동차 세차장", CONFIG.forecast)
    assert not needs_weather_note("과학·기술·회계·세무·세무사", CONFIG.forecast)


# ─────────────────────────── 근거 문장·화법 ───────────────────────────


FORECAST_DETAILS = {
    "TEMP_SHIFT_FORECAST": {"forecast_date": "2026-10-14", "kind": "최저", "today_value": 12.0,
                            "forecast_value": 6.0, "diff": -6.0, "issued": "10월 13일 02시 발표",
                            "valid_until": "2026-10-14"},
    "SEASON_SHIFT_FORECAST": {"near_start": "2026-10-13", "near_end": "2026-10-16", "near_mean": 12.8,
                              "far_start": "2026-10-17", "far_end": "2026-10-22", "far_mean": 6.5, "diff": -6.3,
                              "issued": "10월 13일 02시 발표", "issued_mid": "10월 12일 18시 발표"},
    "FIRST_FREEZE_FORECAST": {"forecast_date": "2026-10-15", "value": -1.5, "origin": "단기",
                              "issued": "10월 13일 02시 발표"},
    "FIRST_HEAT_FORECAST": {"forecast_date": "2026-07-03", "value": 34.0, "origin": "단기",
                            "issued": "7월 2일 02시 발표"},
}


@pytest.mark.parametrize("signal_type", sorted(FORECAST_DETAILS))
def test_forecast_facts_name_the_forecast_and_template_passes_guard(signal_type):
    built = _event_fact(active_event(1, signal_type=signal_type, scope="INDUSTRY", source_name="KMA_FORECAST",
                                     detail=FORECAST_DETAILS[signal_type]))
    assert built is not None
    assert "예보" in built.text and "발표" in built.text
    brief_input = BriefInput(recommendation_id=1, branch_name="강남중앙지점", business_name="예시상점01",
                             industry_name="소매·섬유·의복·신발 소매·여성 의류 소매업", distance_km=0.5,
                             facts=[fact(built.text, "기상청예보", "2026-10-13")],
                             call_reason=built.call_reason, call_purpose=built.call_purpose)
    brief = generate_brief(brief_input, reason_summary=built.summary, llm=None, config=CONFIG.briefing)
    assert len(brief.talk_script) == 3, brief.validation_errors


def test_temp_shift_fact_text():
    built = _event_fact(active_event(1, signal_type="TEMP_SHIFT_FORECAST", scope="INDUSTRY",
                                     detail=FORECAST_DETAILS["TEMP_SHIFT_FORECAST"]))
    assert built is not None
    assert built.text.startswith(
        "기상청 단기예보(10월 13일 02시 발표)에 따르면 10월 14일 최저기온이 6°C로 오늘(12°C)보다 6°C 낮을 것으로 예보되었습니다."
    )


def test_assertive_forecast_sentences_are_blocked():
    facts = [fact("10월 14일 최저기온이 6°C로 예보되었습니다.", "기상청예보", "2026-10-13")]
    kept, errors = validate_script(
        ["내일부터 추워집니다.", "10월 14일 최저기온이 6°C로 예보되어 연락드렸습니다."], facts, CONFIG.briefing
    )
    assert kept == ["10월 14일 최저기온이 6°C로 예보되어 연락드렸습니다."]
    assert any("예보 단정" in error for error in errors)


# ─────────────────────────── 신호별 명부 상한 ───────────────────────────


def _scored(business_id: int, score: float, signal_type: str | None, scope: str = "INDUSTRY") -> ScoredCandidate:
    contributions = [] if signal_type is None else [SignalContribution(
        event_id=1, signal_type=signal_type, scope=scope, weight=1, intensity=1, applicability=1,
        contribution=score)]
    return ScoredCandidate(business_id=business_id, industry_code="X", industry_name="업종", distance_km=0.5,
                           signal_score=score, freshness_score=0.1, proximity=1, scale_fit=1, score=score,
                           reason_tier="INDUSTRY", contributions=contributions)


CAPPED = CONFIG.recommendation.signal_share_capped_types


def test_share_cap_limits_one_macro_signal_and_refills_with_next_candidates():
    scored = [_scored(i, 100 - i, "FX_DAILY_CHANGE") for i in range(1, 16)]
    scored += [_scored(100 + i, 50 - i, "NEW_BUSINESS_OPENING", "BUSINESS") for i in range(1, 4)]
    scored += [_scored(200 + i, 40 - i, None) for i in range(1, 20)]
    ordered, pushed = apply_signal_share_cap(scored, top_n=20, cap_pct=30, capped_types=CAPPED)
    head = ordered[:20]
    assert sum(1 for item in head if item.contributions and item.contributions[0].signal_type == "FX_DAILY_CHANGE") == 6
    assert sum(1 for item in head if item.business_id > 100 and item.business_id < 104) == 3
    assert pushed == {"FX_DAILY_CHANGE": 9}
    assert len(ordered) == len(scored)


def test_share_cap_refills_with_deferred_when_not_enough_candidates():
    scored = [_scored(i, 100 - i, "TEMP_SHIFT_FORECAST") for i in range(1, 11)]
    ordered, pushed = apply_signal_share_cap(scored, top_n=20, cap_pct=30, capped_types=CAPPED)
    assert [item.business_id for item in ordered] == list(range(1, 11))
    assert pushed == {}


def test_share_cap_disabled_without_threshold():
    scored = [_scored(i, 100 - i, "FX_DAILY_CHANGE") for i in range(1, 30)]
    assert apply_signal_share_cap(scored, top_n=20, cap_pct=None, capped_types=CAPPED) == (scored, {})


# ─────────────────────────── 같은 건물 상한 ───────────────────────────


def test_same_address_cap_keeps_two_per_building_and_fills_with_next():
    from backend.batch.targeting.exploration import building_key

    scored = [_scored(i, 100 - i, "NEW_BUSINESS_OPENING", "BUSINESS") for i in range(1, 26)]
    # 1~5번은 같은 건물(층·참고항목만 다름), 나머지는 각자 다른 주소
    address_of: dict[int, str | None] = {
        i: f"서울특별시 중구 을지로 100, {i}층 (을지로2가)" for i in range(1, 6)
    }
    address_of.update({i: f"서울특별시 중구 세종대로 {i}" for i in range(6, 26)})
    ordered, pushed = apply_signal_share_cap(
        scored, top_n=20, cap_pct=None, capped_types=[], address_of=address_of, same_address_cap=2
    )
    head = ordered[:20]
    assert [item.business_id for item in head] == [1, 2] + list(range(6, 24))
    assert pushed == {"SAME_ADDRESS": 3}
    # 상한에 걸린 3곳은 뒤에도 남기지 않는다
    assert {3, 4, 5}.isdisjoint(item.business_id for item in ordered)
    assert building_key("서울특별시 중구 을지로 100, 3층 (을지로2가)") == "서울특별시 중구 을지로 100"
    assert building_key(None) is None


def test_same_address_cap_allows_short_list_when_candidates_run_out():
    scored = [_scored(i, 100 - i, "NEW_BUSINESS_OPENING", "BUSINESS") for i in range(1, 6)]
    address_of: dict[int, str | None] = {i: "서울특별시 구로구 디지털로 300" for i in range(1, 6)}
    ordered, _pushed = apply_signal_share_cap(
        scored, top_n=20, cap_pct=30, capped_types=CAPPED, address_of=address_of, same_address_cap=2
    )
    assert [item.business_id for item in ordered] == [1, 2]


def test_same_address_cap_ignores_missing_address_and_combines_with_signal_cap():
    scored = [_scored(i, 100 - i, "FX_DAILY_CHANGE") for i in range(1, 11)]
    scored += [_scored(100 + i, 50 - i, None) for i in range(1, 20)]
    address_of: dict[int, str | None] = {i: None for i in range(1, 11)}
    ordered, pushed = apply_signal_share_cap(
        scored, top_n=20, cap_pct=30, capped_types=CAPPED, address_of=address_of, same_address_cap=2
    )
    head = ordered[:20]
    assert sum(1 for item in head if item.contributions) == 6
    assert pushed == {"FX_DAILY_CHANGE": 4}


# ─────────────────────────── 같은 가게 중복 제거 (10/14 테스트 결과 3번) ───────────────────────────


def test_duplicate_store_keeps_only_highest_score():
    # 성당지점 '스위트호텔'(성당로 161)이 4·5위에 두 번 나온 사례
    scored = [_scored(i, 100 - i, "NEW_BUSINESS_OPENING", "BUSINESS") for i in range(1, 26)]
    address_of: dict[int, str | None] = {i: f"대구광역시 남구 앞산순환로 {i}" for i in range(1, 26)}
    name_of: dict[int, str | None] = {i: f"가게{i}" for i in range(1, 26)}
    address_of[4] = "대구광역시 달서구 성당로 161"
    address_of[5] = "대구광역시 달서구 성당로 161, 1층 (성당동)"
    name_of[4] = "스위트호텔"
    name_of[5] = "스위트 호텔"
    ordered, pushed = apply_signal_share_cap(
        scored, top_n=20, cap_pct=30, capped_types=CAPPED,
        address_of=address_of, same_address_cap=2, name_of=name_of,
    )
    head = [item.business_id for item in ordered[:20]]
    assert 4 in head and 5 not in head
    assert 5 not in {item.business_id for item in ordered}
    assert head == [1, 2, 3, 4] + list(range(6, 22))
    assert pushed == {"DUPLICATE": 1}


def test_duplicate_removal_works_without_other_caps_and_ignores_missing_name():
    scored = [_scored(i, 100 - i, None) for i in range(1, 6)]
    address_of: dict[int, str | None] = {i: "서울특별시 중구 을지로 100" for i in range(1, 6)}
    name_of: dict[int, str | None] = {1: "카페A", 2: "카페a", 3: None, 4: "", 5: "카페B"}
    ordered, pushed = apply_signal_share_cap(
        scored, top_n=20, cap_pct=None, capped_types=[], address_of=address_of, name_of=name_of,
    )
    assert [item.business_id for item in ordered] == [1, 3, 4, 5]
    assert pushed == {"DUPLICATE": 1}


def test_area_new_openings_is_signal_share_capped():
    assert "AREA_NEW_OPENINGS" in CAPPED
