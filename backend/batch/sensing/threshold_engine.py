"""임계치 판정 (도메인 정의서 5.1절 1단계, RULE-SENSE-03). LLM 호출 없음.

승격 조건은 raw_value가 THRESHOLD_CONFIG.threshold_value를 **초과**하는 것이다(같으면 승격하지 않음).
임계치가 설정되지 않은 신호종류는 승격하지 않는다(초기 데이터 누락을 조용히 통과시키지 않기 위함).
"""

from __future__ import annotations

from backend.common.schemas.signal import SignalDraft


def exceeds_threshold(signal: SignalDraft, thresholds: dict[str, float]) -> tuple[bool, float | None]:
    threshold = thresholds.get(signal.signal_type)
    if threshold is None:
        return False, None
    return signal.raw_value > threshold, threshold
