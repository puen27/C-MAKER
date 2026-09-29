"""구조화 로그 설정 (OPS-08). LOG_DIR 지정 시 <LOG_DIR>/<name>.log, 아니면 stdout (JSON 한 줄)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from backend.common.config import get_settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(name: str) -> logging.Logger:
    root = logging.getLogger()
    if not getattr(root, "_cmaker_configured", False):
        root.setLevel(logging.INFO)
        formatter = JsonFormatter()
        log_dir = get_settings().log_dir
        # LOG_DIR가 있으면 파일로만 쓴다(cron 리다이렉트·journald와 중복 기록 방지). 없으면 stdout.
        if log_dir:
            Path(log_dir).mkdir(parents=True, exist_ok=True)
            handler: logging.Handler = logging.FileHandler(Path(log_dir) / f"{name}.log", encoding="utf-8")
        else:
            handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root.addHandler(handler)
        root._cmaker_configured = True  # type: ignore[attr-defined]
    return logging.getLogger(name)


def log_fields(logger: logging.Logger, level: int, message: str, **fields: object) -> None:
    """단계별 처리 건수·소요시간·실패 소스 등을 필드로 남긴다."""
    logger.log(level, message, extra={"fields": fields})
