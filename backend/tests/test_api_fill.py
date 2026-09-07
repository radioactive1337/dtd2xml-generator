"""Tests for XML fill API."""

from pathlib import Path

from fastapi.testclient import TestClient
from lxml import etree
from pytest import MonkeyPatch

from app.api.routes import dtd as dtd_routes
from app.core.xml_builder import BuildConfig, build_xml

FIXTURES = Path(__file__).parent / "fixtures"

_DB_MAPPING = {
    "query": "SELECT 1 AS id FROM dual",
    "target_element": "PayDoc",
    "fields": {"id": "id"},
    "db_alias": "TEST_DB",
}


def _dev_user():
    from app.user_context import dev_user_context

    return dev_user_context()


def _use_empty_user_connections(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("app.config._find_legacy_connections_file", lambda: None)


def _upload_fixture(client: TestClient) -> str:
    from app.config import shared_dtd_dir

    dtd_dir = shared_dtd_dir()
    dtd_dir.mkdir(parents=True, exist_ok=True)
    (dtd_dir / "types.dtd").write_bytes((FIXTURES / "types.dtd").read_bytes())

    dtd_path = FIXTURES / "main.dtd"
    with dtd_path.open("rb") as f:
        response = client.post(
            "/api/dtd/upload",
            files=[("files", ("main.dtd", f, "application/xml-dtd"))],
        )
    assert response.status_code == 200, response.text
    return response.json()["primary_schema_id"]


def _skeleton_xml(schema_id: str) -> str:
    schema = dtd_routes._user_registry(_dev_user())[schema_id]
    return build_xml(schema, BuildConfig(root_element="PayDoc", mode="minimal")).xml_text


def _mock_llm_alias(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.routes.fill.resolve_llm_alias",
        lambda user, alias="default": "MOCK",
    )


def test_legacy_faker_strategy_rejected(client: TestClient):
    schema_id = _upload_fixture(client)
    response = client.post(
        "/api/fill",
        json={
            "schema_id": schema_id,
            "xml_text": _skeleton_xml(schema_id),
            "strategy": "faker",
        },
    )
    assert response.status_code == 422


def test_ai_fill_requires_llm_aliases(client: TestClient, monkeypatch: MonkeyPatch):
    _use_empty_user_connections(monkeypatch)
    schema_id = _upload_fixture(client)
    xml_text = _skeleton_xml(schema_id)

    response = client.post(
        "/api/fill",
        json={
            "schema_id": schema_id,
            "xml_text": xml_text,
            "strategy": "ai",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "No LLM aliases configured"


def test_git_ai_db_requires_sql_mappings(
    client: TestClient,
    monkeypatch: MonkeyPatch,
):
    _mock_llm_alias(monkeypatch)
    schema_id = _upload_fixture(client)

    response = client.post(
        "/api/fill",
        json={
            "schema_id": schema_id,
            "xml_text": _skeleton_xml(schema_id),
            "strategy": "git_ai_db",
        },
    )

    assert response.status_code == 400
    assert "sql_mappings" in response.json()["detail"]


def test_git_ai_db_runs_db_then_git_then_llm(
    client: TestClient,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
):
    schema_id = _upload_fixture(client)
    xml_text = _skeleton_xml(schema_id)
    stages: list[str] = []

    _mock_llm_alias(monkeypatch)

    async def fake_db(user, xml, mappings, fill_empty_only=False, schema=None):
        stages.append("db")
        assert mappings
        return xml, frozenset(), []

    async def fake_git(xml, schema, **kwargs):
        stages.append("git")
        return xml, frozenset(), [], {"PayDoc@id": "git:ref.xml"}

    async def fake_llm(xml, schema, user, alias="default", **kwargs):
        stages.append("llm")
        return xml

    monkeypatch.setattr("app.api.routes.fill.apply_db_overrides", fake_db)
    monkeypatch.setattr("app.api.routes.fill.populate_from_git", fake_git)
    monkeypatch.setattr("app.api.routes.fill.populate_with_llm", fake_llm)
    monkeypatch.setattr("app.api.routes.fill.reference_xml_root", lambda: tmp_path)

    response = client.post(
        "/api/fill",
        json={
            "schema_id": schema_id,
            "xml_text": xml_text,
            "strategy": "git_ai_db",
            "sql_mappings": [_DB_MAPPING],
        },
    )

    assert response.status_code == 200, response.text
    assert stages == ["db", "git", "llm"]
    data = response.json()
    assert data["strategy"] == "git_ai_db"
    assert data["provenance"] == {"PayDoc@id": "git:ref.xml"}


def test_git_ai_skips_db_stage(
    client: TestClient,
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
):
    schema_id = _upload_fixture(client)
    xml_text = _skeleton_xml(schema_id)

    _mock_llm_alias(monkeypatch)

    async def fake_db(*args, **kwargs):
        raise AssertionError("DB stage should not run for git_ai")

    async def fake_git(xml, schema, **kwargs):
        return xml, frozenset(), [], {}

    async def fake_llm(xml, schema, user, alias="default", **kwargs):
        return xml

    monkeypatch.setattr("app.api.routes.fill.apply_db_overrides", fake_db)
    monkeypatch.setattr("app.api.routes.fill.populate_from_git", fake_git)
    monkeypatch.setattr("app.api.routes.fill.populate_with_llm", fake_llm)
    monkeypatch.setattr("app.api.routes.fill.reference_xml_root", lambda: tmp_path)

    response = client.post(
        "/api/fill",
        json={
            "schema_id": schema_id,
            "xml_text": xml_text,
            "strategy": "git_ai",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["strategy"] == "git_ai"


def test_ai_fill_prefills_empty_enum_before_llm_runs(
    client: TestClient,
    monkeypatch: MonkeyPatch,
):
    schema_id = _upload_fixture(client)
    _mock_llm_alias(monkeypatch)

    # status is an ENUM (%Status; = active|inactive|pending); cleared to "" here
    # to simulate the editor's "clear attribute values" action on a selection.
    xml_text = (
        '<PayDoc id="doc-1" kladr="7700000000000" active="true" status="">'
        '<Header version="1.0"><Title>t</Title></Header>'
        '<Body><Record><Field name="amount" type="number">1</Field></Record></Body>'
        "</PayDoc>"
    )

    async def fake_llm(xml, schema, user, alias="default", **kwargs):
        # Echo back unchanged — the enum must already be valid by this point,
        # proving the pre-fill step ran before the LLM stage.
        return xml

    monkeypatch.setattr("app.api.routes.fill.populate_with_llm", fake_llm)

    response = client.post(
        "/api/fill",
        json={
            "schema_id": schema_id,
            "xml_text": xml_text,
            "strategy": "ai",
        },
    )

    assert response.status_code == 200, response.text
    result_root = etree.fromstring(response.json()["xml_text"].encode("utf-8"))
    assert result_root.get("status") in {"active", "inactive", "pending"}


def test_ai_fill_preserves_original_element_structure(
    client: TestClient,
    monkeypatch: MonkeyPatch,
):
    schema_id = _upload_fixture(client)
    _mock_llm_alias(monkeypatch)

    xml_text = (
        '<PayDoc id="doc-1" kladr="7700000000000" active="true" status="active">'
        '<Header version="1.0"><Title></Title></Header>'
        '<Body><Record><Field name="" type="number"/></Record></Body>'
        "</PayDoc>"
    )

    async def fake_llm(xml, schema, user, alias="default", **kwargs):
        return (
            '<PayDoc id="filled-id" kladr="7700000000000" active="true" status="active" extra="nope">'
            "unwanted-root-text"
            '<Header version="1.0"><Title>Hello</Title></Header>'
            '<Body><Record><Field name="amount" type="number">999</Field>'
            "<Hallucinated/></Record></Body>"
            "<Extra/>"
            "</PayDoc>"
        )

    monkeypatch.setattr("app.api.routes.fill.populate_with_llm", fake_llm)

    response = client.post(
        "/api/fill",
        json={
            "schema_id": schema_id,
            "xml_text": xml_text,
            "strategy": "ai",
        },
    )

    assert response.status_code == 200, response.text
    root = etree.fromstring(response.json()["xml_text"].encode("utf-8"))
    assert root.get("id") == "filled-id"
    assert "extra" not in root.attrib
    assert (root.text or "").strip() != "unwanted-root-text"
    assert root.find("Extra") is None
    assert root.find("Body/Record/Hallucinated") is None
    title = root.find("Header/Title")
    assert title is not None
    assert (title.text or "").strip() == "Hello"
    field = root.find("Body/Record/Field")
    assert field is not None
    assert field.get("name") == "amount"
    assert (field.text or "").strip() == "999"

