"""DATA_SOURCE_SNAPSHOT 적재/조회 (재현성 요건, OPS-05, RULE-SENSE-04 폴백).

원본 응답은 가공 전에 먼저 이 저장소에 적재한다(CLAUDE.md §1). 동일 소스·기준일·원본(해시)은
한 번만 적재하고 기존 ID를 돌려주므로, 수동 재실행이 같은 원본으로 신호를 중복 생성하지 않는다.
요청 파라미터에는 인증키를 넣지 않는다(커넥터가 키를 제외한 값만 넘긴다).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import psycopg
from pydantic import BaseModel

from backend.common.config import get_settings


class SnapshotRecord(BaseModel):
    id: int
    source_name: str
    as_of_date: date
    fetched_at: datetime
    raw_payload: Any


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def save_snapshot(
    conn: psycopg.Connection,
    source_name: str,
    as_of_date: date,
    raw_payload: Any,
    request_params: dict[str, Any] | None = None,
) -> int:
    payload_json = _canonical_json(raw_payload)
    payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    row = conn.execute(
        """
        INSERT INTO data_source_snapshot (source_name, as_of_date, request_params, payload_hash, raw_payload)
        VALUES (%s, %s, %s::jsonb, %s, %s::jsonb)
        ON CONFLICT (source_name, as_of_date, payload_hash)
            DO UPDATE SET source_name = EXCLUDED.source_name
        RETURNING id
        """,
        (source_name, as_of_date, _canonical_json(request_params or {}), payload_hash, payload_json),
    ).fetchone()
    assert row is not None
    return int(row["id"])


def find_latest_snapshot(
    conn: psycopg.Connection, source_name: str, on_or_before: date
) -> SnapshotRecord | None:
    """RULE-SENSE-04 폴백: 기준일이 `on_or_before` 이하인 가장 최근 스냅샷."""
    row = conn.execute(
        """
        SELECT id, source_name, as_of_date, fetched_at, raw_payload
        FROM data_source_snapshot
        WHERE source_name = %s AND as_of_date <= %s
        ORDER BY as_of_date DESC, id DESC
        LIMIT 1
        """,
        (source_name, on_or_before),
    ).fetchone()
    return SnapshotRecord.model_validate(row) if row else None


def get_snapshot(conn: psycopg.Connection, snapshot_id: int) -> SnapshotRecord | None:
    row = conn.execute(
        "SELECT id, source_name, as_of_date, fetched_at, raw_payload FROM data_source_snapshot WHERE id = %s",
        (snapshot_id,),
    ).fetchone()
    return SnapshotRecord.model_validate(row) if row else None


def _hash_file(file_path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _verify_archived_file(target: Path, expected_hash: str, expected_size: int) -> None:
    actual_hash, actual_size = _hash_file(target)
    if actual_hash != expected_hash or actual_size != expected_size:
        raise RuntimeError(
            f"기존 snapshot archive 내용이 예상과 다릅니다: path={target}, "
            f"expected_size={expected_size}, actual_size={actual_size}"
        )


def archive_source_file(source_name: str, as_of_date: date, file_path: Path) -> dict[str, Any]:
    """파일형 원본을 SHA-256 기반 불변 경로에 원자적으로 보관하고 메타데이터를 반환한다."""
    source_hash, source_size = _hash_file(file_path)
    archive_dir = Path(get_settings().snapshot_archive_dir) / source_name / as_of_date.isoformat()
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / f"{file_path.stem}.{source_hash}{file_path.suffix}"

    if target.exists():
        _verify_archived_file(target, source_hash, source_size)
    else:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=archive_dir,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as destination, file_path.open("rb") as source:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
                destination.flush()
                os.fsync(destination.fileno())
            _verify_archived_file(temporary_path, source_hash, source_size)
            if target.exists():
                _verify_archived_file(target, source_hash, source_size)
            else:
                os.replace(temporary_path, target)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    return {
        "archived_path": str(target),
        "original_name": file_path.name,
        "sha256": source_hash,
        "size_bytes": source_size,
    }
