"""Tests for XML fill API."""

from pathlib import Path

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.api.routes import dtd as dtd_routes
from app.core.xml_builder import BuildConfig, build_xml

FIXTURES = Path(__file__).parent / "fixtures"


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


def test_faker_fill_works_without_llm_aliases(
    client: TestClient,
    monkeypatch: MonkeyPatch,
):
    _use_empty_user_connections(monkeypatch)
    schema_id = _upload_fixture(client)
    xml_text = _skeleton_xml(schema_id)

    response = client.post(
        "/api/fill",
        json={
            "schema_id": schema_id,
            "xml_text": xml_text,
            "strategy": "faker",
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["strategy"] == "faker"
    assert "<PayDoc" in data["xml_text"]
    assert 'id="' in data["xml_text"]


def test_faker_fill_preserves_existing_values_by_default(
    client: TestClient,
    monkeypatch: MonkeyPatch,
):
    from lxml import etree

    _use_empty_user_connections(monkeypatch)
    schema_id = _upload_fixture(client)
    xml_text = _skeleton_xml(schema_id)
    root = etree.fromstring(xml_text.encode("utf-8"))
    root.set("id", "keep-me")
    xml_text = etree.tostring(root, encoding="unicode")

    response = client.post(
        "/api/fill",
        json={
            "schema_id": schema_id,
            "xml_text": xml_text,
            "strategy": "faker",
        },
    )

    assert response.status_code == 200, response.text
    filled = etree.fromstring(response.json()["xml_text"].encode("utf-8"))
    assert filled.attrib.get("id") == "keep-me"


def test_faker_fill_overwrites_existing_values_when_preserve_disabled(
    client: TestClient,
    monkeypatch: MonkeyPatch,
):
    from lxml import etree

    _use_empty_user_connections(monkeypatch)
    schema_id = _upload_fixture(client)
    xml_text = _skeleton_xml(schema_id)
    root = etree.fromstring(xml_text.encode("utf-8"))
    root.set("id", "keep-me")
    xml_text = etree.tostring(root, encoding="unicode")

    response = client.post(
        "/api/fill",
        json={
            "schema_id": schema_id,
            "xml_text": xml_text,
            "strategy": "faker",
            "preserve_filled": False,
        },
    )

    assert response.status_code == 200, response.text
    filled = etree.fromstring(response.json()["xml_text"].encode("utf-8"))
    assert filled.attrib.get("id") != "keep-me"


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
