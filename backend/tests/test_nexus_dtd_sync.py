"""Tests for Nexus DTD sync, custom overwrite guard, and auto-update."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.routes import dtd as dtd_routes
from app.config import NexusDtdConfig

FIXTURES = Path(__file__).parent / "fixtures"


def _build_jar(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _sample_jar() -> bytes:
    return _build_jar(
        {
            "META-INF/dtd/v2.dtd": (FIXTURES / "v2.dtd").read_bytes(),
            "META-INF/dtd/types.dtd": (FIXTURES / "types.dtd").read_bytes(),
        }
    )


def _seed_types_dtd() -> None:
    from app.config import shared_dtd_dir

    dtd_dir = shared_dtd_dir()
    dtd_dir.mkdir(parents=True, exist_ok=True)
    (dtd_dir / "types.dtd").write_bytes((FIXTURES / "types.dtd").read_bytes())


def _nexus_cfg(**overrides) -> NexusDtdConfig:
    data = {
        "base_url": "https://nexus.example",
        "repository": "maven-releases",
        "group_id": "com.example",
        "artifact_id": "schema-lib",
        "version": "LATEST",
        "inner_path": "META-INF/dtd/",
        "auto_update": True,
        "check_interval_minutes": 60,
        "on_startup": True,
    }
    data.update(overrides)
    return NexusDtdConfig(**data)


@pytest.mark.asyncio
async def test_sync_skips_same_version(monkeypatch: pytest.MonkeyPatch):
    cfg = _nexus_cfg()
    monkeypatch.setattr(dtd_routes, "get_nexus_dtd_config", lambda: cfg)

    dtd_routes._dtd_dir().mkdir(parents=True, exist_ok=True)
    dtd_routes._write_import_meta(
        "Nexus schema-lib:1.2.3",
        source_type="nexus",
        resolved_version="1.2.3",
        artifact_id="schema-lib",
        updated_by="tester",
    )

    resolve = AsyncMock(return_value=("https://nexus.example/schema-lib-1.2.3.jar", "1.2.3"))
    fetch = AsyncMock()
    monkeypatch.setattr(dtd_routes, "resolve_jar_url", resolve)
    monkeypatch.setattr(dtd_routes, "fetch_jar_bytes", fetch)

    status, schema_ids = await dtd_routes.sync_dtd_from_nexus(
        updated_by="tester",
        skip_if_same_version=True,
    )
    assert status == "skipped_same_version"
    assert schema_ids == []
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_updates_when_version_changes(monkeypatch: pytest.MonkeyPatch):
    cfg = _nexus_cfg()
    monkeypatch.setattr(dtd_routes, "get_nexus_dtd_config", lambda: cfg)

    dtd_routes._dtd_dir().mkdir(parents=True, exist_ok=True)
    dtd_routes._write_import_meta(
        "Nexus schema-lib:1.2.3",
        source_type="nexus",
        resolved_version="1.2.3",
        artifact_id="schema-lib",
        updated_by="tester",
    )

    jar_bytes = _sample_jar()
    resolve = AsyncMock(return_value=("https://nexus.example/schema-lib-1.3.0.jar", "1.3.0"))
    fetch = AsyncMock(return_value=jar_bytes)
    monkeypatch.setattr(dtd_routes, "resolve_jar_url", resolve)
    monkeypatch.setattr(dtd_routes, "fetch_jar_bytes", fetch)

    status, schema_ids = await dtd_routes.sync_dtd_from_nexus(
        updated_by="tester",
        skip_if_same_version=True,
    )
    assert status == "updated"
    assert schema_ids
    meta = dtd_routes._read_import_meta()
    assert meta is not None
    assert meta.source_type == "nexus"
    assert meta.resolved_version == "1.3.0"


@pytest.mark.asyncio
async def test_auto_update_skips_custom_source(monkeypatch: pytest.MonkeyPatch):
    cfg = _nexus_cfg(auto_update=True)
    monkeypatch.setattr(dtd_routes, "get_nexus_dtd_config", lambda: cfg)

    dtd_routes._dtd_dir().mkdir(parents=True, exist_ok=True)
    dtd_routes._write_import_meta(
        "Загрузка: main.dtd",
        source_type="upload",
        updated_by="tester",
    )

    resolve = AsyncMock()
    monkeypatch.setattr(dtd_routes, "resolve_jar_url", resolve)

    status = await dtd_routes.auto_update_dtd_from_nexus()
    assert status == "skipped_custom"
    resolve.assert_not_awaited()


def test_upload_rejects_custom_overwrite_without_force(client: TestClient):
    _seed_types_dtd()
    dtd_path = FIXTURES / "main.dtd"
    with dtd_path.open("rb") as f:
        first = client.post(
            "/api/dtd/upload",
            files=[("files", ("main.dtd", f, "application/xml-dtd"))],
        )
    assert first.status_code == 200
    assert first.json()["source_type"] == "upload"

    with dtd_path.open("rb") as f:
        second = client.post(
            "/api/dtd/upload",
            files=[("files", ("main.dtd", f, "application/xml-dtd"))],
        )
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["code"] == "DTD_CUSTOM_OVERWRITE"

    with dtd_path.open("rb") as f:
        forced = client.post(
            "/api/dtd/upload",
            data={"force": "true"},
            files=[("files", ("main.dtd", f, "application/xml-dtd"))],
        )
    assert forced.status_code == 200
    assert forced.json()["source_type"] == "upload"


def test_pull_nexus_requires_force_over_custom(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    _seed_types_dtd()
    dtd_path = FIXTURES / "main.dtd"
    with dtd_path.open("rb") as f:
        upload = client.post(
            "/api/dtd/upload",
            files=[("files", ("main.dtd", f, "application/xml-dtd"))],
        )
    assert upload.status_code == 200

    cfg = _nexus_cfg()
    monkeypatch.setattr(dtd_routes, "get_nexus_dtd_config", lambda: cfg)
    jar_bytes = _sample_jar()
    monkeypatch.setattr(
        dtd_routes,
        "resolve_jar_url",
        AsyncMock(return_value=("https://nexus.example/x.jar", "2.0.0")),
    )
    monkeypatch.setattr(dtd_routes, "fetch_jar_bytes", AsyncMock(return_value=jar_bytes))

    blocked = client.post("/api/dtd/pull-nexus")
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "DTD_CUSTOM_OVERWRITE"

    ok = client.post("/api/dtd/pull-nexus", params={"force": "true"})
    assert ok.status_code == 200
    data = ok.json()
    assert data["source_type"] == "nexus"
    assert data["resolved_version"] == "2.0.0"


def test_infer_legacy_nexus_import_source():
    meta = dtd_routes.DtdImportMeta(
        import_source="Nexus schema-lib:9.9.9",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    assert dtd_routes._resolve_source_type(meta) == "nexus"
