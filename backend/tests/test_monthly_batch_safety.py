from __future__ import annotations

import hashlib
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from backend.batch import run_monthly
from backend.batch.connectors import sbiz_connector
from backend.batch.connectors.http_client import FetchResult, SourceFetchError
from backend.batch.population import business_loader
from backend.batch.population.business_loader import AreaIndex, PermitApplyResult
from backend.common import snapshot_store
from backend.common.schemas.branch import BranchContext
from backend.common.schemas.business import PermitRecord

AS_OF = date(2026, 10, 1)


def _api_page(items: list[dict[str, Any]], total: int) -> dict[str, Any]:
    return {
        "response": {
            "header": {"resultCode": "00"},
            "body": {"items": {"item": items}, "totalCount": total},
        }
    }


def _item(store_id: str, *, name: str = "가상상점", lat: Any = "37.5", lon: Any = "127.0") -> dict[str, Any]:
    return {
        "bizesId": store_id,
        "bizesNm": name,
        "indsLclsCd": "I1",
        "indsLclsNm": "음식",
        "indsMclsCd": "I10",
        "indsMclsNm": "한식",
        "indsSclsCd": "I101",
        "indsSclsNm": "한식",
        "rdnmAdr": "서울특별시 가상로 1",
        "lat": lat,
        "lon": lon,
    }


def _fetch_result(items: list[dict[str, Any]]) -> FetchResult:
    unique_count = len({str(item.get("bizesId") or "").strip() for item in items})
    return FetchResult(
        payload={
            "items": items,
            "complete": True,
            "unique_count": unique_count,
            "total_count": unique_count,
            "pages_fetched": 1,
        },
        request_params={"url": "https://public.invalid/sbiz", "radius": 1000},
    )


def _fetch(monkeypatch: pytest.MonkeyPatch, pages: list[dict[str, Any]]) -> FetchResult:
    responses = iter(pages)
    monkeypatch.setattr(sbiz_connector, "request_json", lambda *args, **kwargs: next(responses))
    return sbiz_connector.fetch_stores_in_radius(
        "test-key",
        "https://public.invalid/sbiz",
        lat=37.5,
        lng=127.0,
        radius_m=1000,
        page_size=2,
    )


def test_sbiz_rejects_total_count_change_between_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SourceFetchError, match="totalCount"):
        _fetch(monkeypatch, [_api_page([_item("A")], 2), _api_page([_item("B")], 3)])


@pytest.mark.parametrize(
    "pages",
    [
        [_api_page([_item("A"), _item("A")], 3)],
        [_api_page([_item("A")], 3), _api_page([_item("A")], 3)],
    ],
)
def test_sbiz_rejects_duplicate_ids_within_or_between_pages(
    monkeypatch: pytest.MonkeyPatch,
    pages: list[dict[str, Any]],
) -> None:
    with pytest.raises(SourceFetchError, match="중복"):
        _fetch(monkeypatch, pages)


def test_sbiz_rejects_page_limit_before_total(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sbiz_connector, "_MAX_PAGES", 2)
    with pytest.raises(SourceFetchError, match="페이지 상한"):
        _fetch(monkeypatch, [_api_page([_item("A")], 3), _api_page([_item("B")], 3)])


def test_sbiz_rejects_early_empty_page(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SourceFetchError, match="빈 페이지"):
        _fetch(monkeypatch, [_api_page([_item("A")], 2), _api_page([], 2)])


def test_sbiz_rejects_result_code_no_data(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "response": {
            "header": {"resultCode": "03", "resultMsg": "NO_DATA"},
            "body": {"items": {"item": []}, "totalCount": 0},
        }
    }

    with pytest.raises(SourceFetchError, match="NO_DATA.*resultCode=03"):
        _fetch(monkeypatch, [payload])


def test_sbiz_accepts_complete_zero_count(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _fetch(monkeypatch, [_api_page([], 0)])

    assert result.payload == {
        "items": [],
        "complete": True,
        "unique_count": 0,
        "total_count": 0,
        "pages_fetched": 1,
    }


def test_sbiz_returns_complete_multi_page_manifest_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _fetch(
        monkeypatch,
        [
            _api_page([_item("A"), _item("B")], 3),
            _api_page([_item("C")], 3),
        ],
    )

    assert [item["bizesId"] for item in result.payload["items"]] == ["A", "B", "C"]
    assert result.payload["complete"] is True
    assert result.payload["unique_count"] == result.payload["total_count"] == 3
    assert result.payload["pages_fetched"] == 2
    assert "serviceKey" not in result.request_params
    assert "test-key" not in str(result.payload)


def _branch(branch_id: int, code: str, *, lat: float = 37.5, lng: float = 127.0) -> BranchContext:
    return BranchContext(
        id=branch_id,
        branch_code=code,
        name=f"가상지점{branch_id}",
        address="서울특별시 가상로",
        lat=lat,
        lng=lng,
        coverage_radius_km=1.0,
        handles_forex=False,
        atm_count=1,
    )


class _TransactionTracker:
    def __init__(self) -> None:
        self.connections: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    @contextmanager
    def connection(self):
        conn = object()
        self.connections.append(conn)
        try:
            yield conn
        except Exception:
            self.rollbacks += 1
            raise
        else:
            self.commits += 1


def _configure_sbiz(
    monkeypatch: pytest.MonkeyPatch,
    *,
    options: dict[str, Any] | None = None,
) -> None:
    monkeypatch.setattr(
        run_monthly,
        "get_settings",
        lambda: SimpleNamespace(data_go_kr_service_key="test-key"),
    )
    monkeypatch.setattr(
        run_monthly,
        "get_pipeline_config",
        lambda: SimpleNamespace(
            sources={
                "SBIZ_STORE": SimpleNamespace(
                    url="https://public.invalid/sbiz",
                    options=(
                        {
                            "min_population_records": 1,
                            "max_population_drop_ratio": 0.5,
                        }
                        if options is None
                        else options
                    ),
                )
            }
        ),
    )
    monkeypatch.setattr(run_monthly, "log_fields", lambda *args, **kwargs: None)


def test_one_branch_failure_preserves_snapshots_but_never_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_sbiz(monkeypatch)
    tracker = _TransactionTracker()
    area = AreaIndex([_branch(1, "000001"), _branch(2, "000002")])
    responses: list[FetchResult | Exception] = [_fetch_result([_item("A")]), ValueError("bad payload")]

    def fetch(*args, **kwargs):
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    snapshots: list[str] = []
    monkeypatch.setattr(run_monthly.sbiz_connector, "fetch_stores_in_radius", fetch)
    monkeypatch.setattr(run_monthly, "get_connection", tracker.connection)
    monkeypatch.setattr(
        run_monthly,
        "save_snapshot",
        lambda conn, source, as_of, payload, params: snapshots.append(params["branch_code"]) or 11,
    )
    monkeypatch.setattr(
        run_monthly,
        "apply_sbiz_records",
        lambda *args: pytest.fail("한 지점이라도 실패하면 BUSINESS publish를 호출하면 안 됩니다"),
    )

    with pytest.raises(run_monthly.MonthlyBatchSafetyError, match="000002"):
        run_monthly.load_sbiz(area, AS_OF)

    assert snapshots == ["000001"]
    assert tracker.commits == 1
    assert tracker.rollbacks == 0


def test_all_branches_publish_global_unique_id_and_close_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_sbiz(monkeypatch)
    tracker = _TransactionTracker()
    area = AreaIndex([
        _branch(1, "000001"),
        _branch(2, "000002", lat=37.5001, lng=127.0001),
    ])
    duplicate = _item("OVERLAP")
    monkeypatch.setattr(
        run_monthly.sbiz_connector,
        "fetch_stores_in_radius",
        lambda *args, **kwargs: _fetch_result([duplicate.copy()]),
    )
    monkeypatch.setattr(run_monthly, "get_connection", tracker.connection)
    snapshot_ids = iter([101, 102])
    monkeypatch.setattr(run_monthly, "save_snapshot", lambda *args, **kwargs: next(snapshot_ids))

    upserts: list[str] = []
    monkeypatch.setattr(
        business_loader.repo,
        "upsert_business_by_sbiz",
        lambda conn, record: upserts.append(record.sbiz_store_id) or 10,
    )
    candidates = [
        {
            "id": 10,
            "sbiz_store_id": "OVERLAP",
            "lat": 37.5,
            "lng": 127.0,
            "status_source": "SBIZ",
            "operating_status": "정상",
        },
        {
            "id": 20,
            "sbiz_store_id": "MISSING",
            "lat": 37.5002,
            "lng": 127.0002,
            "status_source": "SBIZ",
            "operating_status": "정상",
        },
    ]
    monkeypatch.setattr(business_loader.repo, "find_businesses_in_box", lambda *args: candidates)
    close_calls: list[tuple[list[int], set[int]]] = []

    def mark_closed(conn, candidate_ids, seen_ids, checked_on):
        close_calls.append((candidate_ids, seen_ids))
        return 1

    monkeypatch.setattr(business_loader.repo, "mark_sbiz_missing_closed", mark_closed)

    summary = run_monthly.load_sbiz(area, AS_OF)

    assert upserts == ["OVERLAP"]
    assert close_calls == [([10, 20], {10})]
    assert summary["branches"] == 2
    assert summary["total_input"] == 2
    assert summary["unique_count"] == summary["upserted"] == 1
    assert summary["marked_closed"] == 1
    assert summary["existing_candidate_count"] == 2
    assert summary["incoming_count"] == 1
    assert summary["drop_ratio"] == 0.5
    assert summary["publish_complete"] is True
    assert tracker.commits == 3
    assert tracker.rollbacks == 0


def test_conflicting_overlap_payload_never_opens_publish_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_sbiz(monkeypatch)
    tracker = _TransactionTracker()
    area = AreaIndex([_branch(1, "000001"), _branch(2, "000002")])
    results = iter([
        _fetch_result([_item("A", name="첫 이름")]),
        _fetch_result([_item("A", name="다른 이름")]),
    ])
    monkeypatch.setattr(
        run_monthly.sbiz_connector,
        "fetch_stores_in_radius",
        lambda *args, **kwargs: next(results),
    )
    monkeypatch.setattr(run_monthly, "get_connection", tracker.connection)
    monkeypatch.setattr(run_monthly, "save_snapshot", lambda *args, **kwargs: 1)

    with pytest.raises(run_monthly.MonthlyBatchSafetyError, match="payload가 충돌"):
        run_monthly.load_sbiz(area, AS_OF)

    assert tracker.commits == 2
    assert tracker.rollbacks == 0


def test_invalid_sbiz_item_rolls_back_without_upsert_or_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_sbiz(monkeypatch)
    tracker = _TransactionTracker()
    area = AreaIndex([_branch(1, "000001")])
    invalid_item = _item("INVALID", lat=None)
    monkeypatch.setattr(
        run_monthly.sbiz_connector,
        "fetch_stores_in_radius",
        lambda *args, **kwargs: _fetch_result([invalid_item]),
    )
    monkeypatch.setattr(run_monthly, "get_connection", tracker.connection)
    monkeypatch.setattr(run_monthly, "save_snapshot", lambda *args, **kwargs: 1)
    monkeypatch.setattr(
        business_loader.repo,
        "upsert_business_by_sbiz",
        lambda *args: pytest.fail("invalid 검증 전에 upsert하면 안 됩니다"),
    )
    monkeypatch.setattr(
        business_loader.repo,
        "mark_sbiz_missing_closed",
        lambda *args: pytest.fail("invalid 입력으로 누락 폐업을 판정하면 안 됩니다"),
    )

    with pytest.raises(business_loader.PopulationPublishError, match="invalid"):
        run_monthly.load_sbiz(area, AS_OF)

    assert tracker.commits == 1
    assert tracker.rollbacks == 1


def test_configured_permit_directory_without_csv_is_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        run_monthly,
        "get_settings",
        lambda: SimpleNamespace(permit_full_data_dir=str(tmp_path)),
    )

    with pytest.raises(run_monthly.MonthlyBatchSafetyError, match="CSV 파일이 없습니다"):
        run_monthly.load_permit_files(AreaIndex([]), AS_OF)


def _permit_record(name: str) -> PermitRecord:
    return PermitRecord(
        mgt_no=name,
        name=name,
        operating_status="정상",
        x=200000,
        y=450000,
    )


def test_permit_multiple_file_failure_rolls_back_one_apply_transaction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for name in ("a.csv", "b.csv"):
        (input_dir / name).write_text("header\n", encoding="utf-8")
    monkeypatch.setattr(
        run_monthly,
        "get_settings",
        lambda: SimpleNamespace(permit_full_data_dir=str(input_dir)),
    )
    tracker = _TransactionTracker()
    monkeypatch.setattr(run_monthly, "get_connection", tracker.connection)
    order: list[str] = []

    def archive(source, as_of, file_path):
        order.append(f"archive:{file_path.name}")
        return {"archived_path": str(file_path), "original_name": file_path.name, "sha256": "x", "size_bytes": 1}

    def save(conn, source, as_of, payload, params):
        order.append(f"snapshot:{params['file']}")
        return len(order)

    apply_connections: list[object] = []

    def apply(conn, permits, area, as_of):
        apply_connections.append(conn)
        records = list(permits)
        order.append(f"apply:{records[0].name}")
        if len(apply_connections) == 2:
            raise RuntimeError("second file failed")
        return PermitApplyResult(upserted=1)

    monkeypatch.setattr(run_monthly, "archive_source_file", archive)
    monkeypatch.setattr(run_monthly, "save_snapshot", save)
    monkeypatch.setattr(
        run_monthly.permit_connector,
        "fetch_all_businesses",
        lambda file_path: iter([{"name": file_path.stem}]),
    )
    monkeypatch.setattr(run_monthly, "parse_permit_row", lambda row: _permit_record(row["name"]))
    monkeypatch.setattr(run_monthly, "apply_permit_records", apply)
    monkeypatch.setattr(run_monthly, "log_fields", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="second file failed"):
        run_monthly.load_permit_files(AreaIndex([]), AS_OF)

    first_apply = min(index for index, value in enumerate(order) if value.startswith("apply:"))
    last_snapshot = max(index for index, value in enumerate(order) if value.startswith("snapshot:"))
    assert first_apply > last_snapshot
    assert len(apply_connections) == 2
    assert apply_connections[0] is apply_connections[1]
    assert tracker.commits == 2
    assert tracker.rollbacks == 1


def test_permit_success_aggregates_file_and_row_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for name in ("a.csv", "b.csv"):
        (tmp_path / name).write_text("header\n", encoding="utf-8")
    monkeypatch.setattr(
        run_monthly,
        "get_settings",
        lambda: SimpleNamespace(permit_full_data_dir=str(tmp_path)),
    )
    tracker = _TransactionTracker()
    monkeypatch.setattr(run_monthly, "get_connection", tracker.connection)
    monkeypatch.setattr(
        run_monthly,
        "archive_source_file",
        lambda source, as_of, path: {
            "archived_path": str(path),
            "original_name": path.name,
            "sha256": "x",
            "size_bytes": 1,
        },
    )
    monkeypatch.setattr(run_monthly, "save_snapshot", lambda *args, **kwargs: 1)
    monkeypatch.setattr(
        run_monthly.permit_connector,
        "fetch_all_businesses",
        lambda path: iter([{"name": path.stem}]),
    )
    monkeypatch.setattr(run_monthly, "parse_permit_row", lambda row: _permit_record(row["name"]))

    def apply(conn, permits, area, as_of):
        assert len(list(permits)) == 1
        return PermitApplyResult(upserted=1, skipped_out_of_area=1)

    monkeypatch.setattr(run_monthly, "apply_permit_records", apply)
    monkeypatch.setattr(run_monthly, "log_fields", lambda *args, **kwargs: None)

    summary = run_monthly.load_permit_files(AreaIndex([]), AS_OF)

    assert summary["files"] == 2
    assert summary["rows"] == summary["parsed_rows"] == 2
    assert summary["upserted"] == summary["skipped_out_of_area"] == 2
    assert summary["publish_complete"] is True
    assert tracker.commits == 3
    assert tracker.rollbacks == 0


def test_archive_uses_immutable_content_addressed_paths_and_reuses_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive_dir = tmp_path / "archive"
    monkeypatch.setattr(
        snapshot_store,
        "get_settings",
        lambda: SimpleNamespace(snapshot_archive_dir=str(archive_dir)),
    )
    sources = [tmp_path / folder / "business.csv" for folder in ("one", "two", "three")]
    for source in sources:
        source.parent.mkdir()
    sources[0].write_bytes(b"first-content")
    sources[1].write_bytes(b"second-content")
    sources[2].write_bytes(b"first-content")

    first = snapshot_store.archive_source_file("PERMIT_FULL", AS_OF, sources[0])
    second = snapshot_store.archive_source_file("PERMIT_FULL", AS_OF, sources[1])
    reused = snapshot_store.archive_source_file("PERMIT_FULL", AS_OF, sources[2])
    first_path = Path(first["archived_path"])
    second_path = Path(second["archived_path"])

    assert first_path != second_path
    assert Path(reused["archived_path"]) == first_path
    assert first_path.read_bytes() == b"first-content"
    assert second_path.read_bytes() == b"second-content"
    assert first["sha256"] in first_path.name
    assert second["sha256"] in second_path.name
    assert first["original_name"] == second["original_name"] == "business.csv"
    assert first["size_bytes"] == len(b"first-content")


def test_archive_refuses_to_overwrite_corrupt_existing_content_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    archive_dir = tmp_path / "archive"
    monkeypatch.setattr(
        snapshot_store,
        "get_settings",
        lambda: SimpleNamespace(snapshot_archive_dir=str(archive_dir)),
    )
    source = tmp_path / "business.csv"
    source.write_bytes(b"expected")
    digest = hashlib.sha256(b"expected").hexdigest()
    target_dir = archive_dir / "PERMIT_FULL" / AS_OF.isoformat()
    target_dir.mkdir(parents=True)
    target = target_dir / f"business.{digest}.csv"
    target.write_bytes(b"do-not-overwrite")

    with pytest.raises(RuntimeError, match="기존 snapshot archive"):
        snapshot_store.archive_source_file("PERMIT_FULL", AS_OF, source)

    assert target.read_bytes() == b"do-not-overwrite"


def test_main_returns_one_on_atomic_publish_failure_while_lock_is_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = False
    logs: list[tuple[str, bool]] = []

    @contextmanager
    def acquire(lock_key: int):
        nonlocal held
        held = True
        try:
            yield True
        finally:
            held = False

    monkeypatch.setattr(run_monthly, "setup_logging", lambda name: None)
    monkeypatch.setattr(run_monthly, "acquire_advisory_lock", acquire)
    monkeypatch.setattr(
        run_monthly,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(run_monthly.MonthlyBatchSafetyError("unsafe")),
    )
    monkeypatch.setattr(
        run_monthly,
        "log_fields",
        lambda logger, level, message, **kwargs: logs.append((message, held)),
    )
    monkeypatch.setattr(run_monthly, "close_pool", lambda: None)

    assert run_monthly.main([]) == 1
    assert held is False
    assert ("월간 모집단 적재 실패", True) in logs


def test_permit_apply_reads_immutable_archive_after_original_is_replaced(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    archive_dir = tmp_path / "archive"
    input_dir.mkdir()
    archive_dir.mkdir()
    original = input_dir / "permit.csv"
    original.write_text("archived-bytes", encoding="utf-8")
    archived_path = archive_dir / "permit.immutable.csv"
    tracker = _TransactionTracker()
    parser_paths: list[Path] = []
    applied_names: list[str] = []

    monkeypatch.setattr(
        run_monthly,
        "get_settings",
        lambda: SimpleNamespace(permit_full_data_dir=str(input_dir)),
    )
    monkeypatch.setattr(run_monthly, "get_connection", tracker.connection)

    def archive(source, as_of, file_path):
        archived_path.write_bytes(file_path.read_bytes())
        file_path.write_text("replaced-original", encoding="utf-8")
        return {
            "archived_path": str(archived_path),
            "original_name": file_path.name,
            "sha256": "immutable",
            "size_bytes": archived_path.stat().st_size,
        }

    def fetch(path: Path):
        parser_paths.append(path)
        return iter([{"name": path.read_text(encoding="utf-8")}])

    def apply(conn, permits, area, as_of):
        applied_names.extend(record.name for record in permits)
        return PermitApplyResult(upserted=1)

    monkeypatch.setattr(run_monthly, "archive_source_file", archive)
    monkeypatch.setattr(run_monthly, "save_snapshot", lambda *args, **kwargs: 1)
    monkeypatch.setattr(run_monthly.permit_connector, "fetch_all_businesses", fetch)
    monkeypatch.setattr(run_monthly, "parse_permit_row", lambda row: _permit_record(row["name"]))
    monkeypatch.setattr(run_monthly, "apply_permit_records", apply)
    monkeypatch.setattr(run_monthly, "log_fields", lambda *args, **kwargs: None)

    summary = run_monthly.load_permit_files(AreaIndex([]), AS_OF)

    assert parser_paths == [archived_path]
    assert applied_names == ["archived-bytes"]
    assert original.read_text(encoding="utf-8") == "replaced-original"
    assert summary["files"] == 1
    assert tracker.commits == 2


@pytest.mark.parametrize(
    "archive_meta",
    [
        {"original_name": "permit.csv", "sha256": "x", "size_bytes": 1},
        {
            "archived_path": "missing-archive.csv",
            "original_name": "permit.csv",
            "sha256": "x",
            "size_bytes": 1,
        },
    ],
)
def test_missing_archive_path_fails_before_any_database_transaction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    archive_meta: dict[str, object],
) -> None:
    original = tmp_path / "permit.csv"
    original.write_text("header", encoding="utf-8")
    tracker = _TransactionTracker()
    monkeypatch.setattr(
        run_monthly,
        "get_settings",
        lambda: SimpleNamespace(permit_full_data_dir=str(tmp_path)),
    )
    monkeypatch.setattr(run_monthly, "archive_source_file", lambda *args: archive_meta)
    monkeypatch.setattr(run_monthly, "get_connection", tracker.connection)

    with pytest.raises(run_monthly.MonthlyBatchSafetyError, match="archive"):
        run_monthly.load_permit_files(AreaIndex([]), AS_OF)

    assert tracker.connections == []


def test_monthly_run_without_coordinate_branches_fails_before_source_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @contextmanager
    def connection():
        yield object()

    branch_without_coordinates = _branch(1, "000001").model_copy(update={"lat": None, "lng": None})
    monkeypatch.setattr(run_monthly, "setup_logging", lambda name: None)
    monkeypatch.setattr(run_monthly, "get_connection", connection)
    monkeypatch.setattr(run_monthly.repo, "load_current_branches", lambda conn: [branch_without_coordinates])
    monkeypatch.setattr(
        run_monthly,
        "load_sbiz",
        lambda *args: pytest.fail("좌표 보유 지점이 없으면 source를 호출하면 안 됩니다"),
    )
    monkeypatch.setattr(
        run_monthly,
        "load_permit_files",
        lambda *args: pytest.fail("좌표 보유 지점이 없으면 source를 호출하면 안 됩니다"),
    )
    monkeypatch.setattr(run_monthly, "log_fields", lambda *args, **kwargs: None)

    with pytest.raises(run_monthly.MonthlyBatchSafetyError, match="좌표 보유 지점이 0건"):
        run_monthly.run(AS_OF)


def _existing_sbiz_rows(count: int) -> list[dict[str, Any]]:
    return [
        {
            "id": index,
            "sbiz_store_id": f"S{index}",
            "lat": 37.5,
            "lng": 127.0,
            "status_source": "SBIZ",
            "operating_status": "정상",
        }
        for index in range(1, count + 1)
    ]


def test_sbiz_complete_zero_manifest_rolls_back_publish_without_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_sbiz(monkeypatch)
    tracker = _TransactionTracker()
    area = AreaIndex([_branch(1, "000001")])
    monkeypatch.setattr(
        run_monthly.sbiz_connector,
        "fetch_stores_in_radius",
        lambda *args, **kwargs: _fetch_result([]),
    )
    monkeypatch.setattr(run_monthly, "get_connection", tracker.connection)
    monkeypatch.setattr(run_monthly, "save_snapshot", lambda *args, **kwargs: 1)
    monkeypatch.setattr(business_loader.repo, "find_businesses_in_box", lambda *args: [])
    monkeypatch.setattr(
        business_loader.repo,
        "upsert_business_by_sbiz",
        lambda *args: pytest.fail("최소 모집단 가드 실패 후 upsert하면 안 됩니다"),
    )
    monkeypatch.setattr(
        business_loader.repo,
        "mark_sbiz_missing_closed",
        lambda *args: pytest.fail("최소 모집단 가드 실패 후 폐업 처리하면 안 됩니다"),
    )

    with pytest.raises(business_loader.PopulationPublishError, match="최소 건수"):
        run_monthly.load_sbiz(area, AS_OF)

    assert tracker.commits == 1
    assert tracker.rollbacks == 1


def test_sbiz_blocks_sixty_percent_drop_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tracker = _TransactionTracker()
    area = AreaIndex([_branch(1, "000001")])
    monkeypatch.setattr(
        business_loader.repo,
        "find_businesses_in_box",
        lambda *args: _existing_sbiz_rows(10),
    )
    monkeypatch.setattr(
        business_loader.repo,
        "upsert_business_by_sbiz",
        lambda *args: pytest.fail("감소율 가드 실패 후 upsert하면 안 됩니다"),
    )
    monkeypatch.setattr(
        business_loader.repo,
        "mark_sbiz_missing_closed",
        lambda *args: pytest.fail("감소율 가드 실패 후 폐업 처리하면 안 됩니다"),
    )

    with pytest.raises(business_loader.PopulationPublishError, match="감소 비율"):
        with tracker.connection() as conn:
            business_loader.apply_sbiz_records(
                conn,  # type: ignore[arg-type]
                [_item(f"S{index}") for index in range(1, 5)],
                area,
                AS_OF,
                min_population_records=1,
                max_population_drop_ratio=0.5,
            )

    assert tracker.commits == 0
    assert tracker.rollbacks == 1


def test_sbiz_allows_exactly_fifty_percent_drop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    area = AreaIndex([_branch(1, "000001")])
    monkeypatch.setattr(
        business_loader.repo,
        "find_businesses_in_box",
        lambda *args: _existing_sbiz_rows(10),
    )
    upserts: list[str] = []

    def upsert(conn: object, record: Any) -> int:
        store_id = str(record.sbiz_store_id)
        upserts.append(store_id)
        return int(store_id.removeprefix("S"))

    close_calls: list[tuple[list[int], set[int]]] = []
    monkeypatch.setattr(business_loader.repo, "upsert_business_by_sbiz", upsert)
    monkeypatch.setattr(
        business_loader.repo,
        "mark_sbiz_missing_closed",
        lambda conn, candidates, seen, checked_on: close_calls.append((candidates, seen)) or 5,
    )

    result = business_loader.apply_sbiz_records(
        object(),  # type: ignore[arg-type]
        [_item(f"S{index}") for index in range(1, 6)],
        area,
        AS_OF,
        min_population_records=1,
        max_population_drop_ratio=0.5,
    )

    assert upserts == ["S1", "S2", "S3", "S4", "S5"]
    assert close_calls == [(list(range(1, 11)), set(range(1, 6)))]
    assert result.existing_candidate_count == 10
    assert result.incoming_count == 5
    assert result.drop_ratio == 0.5
    assert result.marked_closed == 5


def test_sbiz_allows_initial_population_with_one_incoming_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    area = AreaIndex([_branch(1, "000001")])
    monkeypatch.setattr(business_loader.repo, "find_businesses_in_box", lambda *args: [])
    monkeypatch.setattr(business_loader.repo, "upsert_business_by_sbiz", lambda *args: 101)
    close_calls: list[tuple[list[int], set[int]]] = []
    monkeypatch.setattr(
        business_loader.repo,
        "mark_sbiz_missing_closed",
        lambda conn, candidates, seen, checked_on: close_calls.append((candidates, seen)) or 0,
    )

    result = business_loader.apply_sbiz_records(
        object(),  # type: ignore[arg-type]
        [_item("NEW")],
        area,
        AS_OF,
        min_population_records=1,
        max_population_drop_ratio=0.5,
    )

    assert close_calls == [([], {101})]
    assert result.existing_candidate_count == 0
    assert result.incoming_count == 1
    assert result.drop_ratio == 0.0
    assert result.upserted == 1


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"min_population_records": 0, "max_population_drop_ratio": 0.5},
        {"min_population_records": 1.0, "max_population_drop_ratio": 0.5},
        {"min_population_records": 1, "max_population_drop_ratio": -0.1},
        {"min_population_records": 1, "max_population_drop_ratio": 1.0},
        {"min_population_records": 1, "max_population_drop_ratio": "0.5"},
    ],
)
def test_sbiz_invalid_publish_options_fail_before_source_fetch(
    monkeypatch: pytest.MonkeyPatch,
    options: dict[str, Any],
) -> None:
    _configure_sbiz(monkeypatch, options=options)
    monkeypatch.setattr(
        run_monthly.sbiz_connector,
        "fetch_stores_in_radius",
        lambda *args, **kwargs: pytest.fail("잘못된 설정으로 source를 호출하면 안 됩니다"),
    )

    with pytest.raises(run_monthly.MonthlyBatchSafetyError):
        run_monthly.load_sbiz(AreaIndex([_branch(1, "000001")]), AS_OF)


@pytest.mark.parametrize(
    ("min_records", "max_drop_ratio"),
    [(0, 0.5), (True, 0.5), (1, -0.1), (1, 1.0), (1, True)],
)
def test_sbiz_apply_revalidates_invalid_publish_limits(
    monkeypatch: pytest.MonkeyPatch,
    min_records: Any,
    max_drop_ratio: Any,
) -> None:
    monkeypatch.setattr(
        business_loader.repo,
        "find_businesses_in_box",
        lambda *args: pytest.fail("잘못된 설정으로 DB 후보를 조회하면 안 됩니다"),
    )

    with pytest.raises(business_loader.PopulationPublishError):
        business_loader.apply_sbiz_records(
            object(),  # type: ignore[arg-type]
            [_item("A")],
            AreaIndex([_branch(1, "000001")]),
            AS_OF,
            min_population_records=min_records,
            max_population_drop_ratio=max_drop_ratio,
        )
