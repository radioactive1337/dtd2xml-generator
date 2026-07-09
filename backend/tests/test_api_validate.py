"""Tests for XML validation API."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.api.routes import dtd as dtd_routes
from app.core.xml_builder import BuildConfig, build_xml

FIXTURES = Path(__file__).parent / "fixtures"


def _dev_user():
    from app.user_context import dev_user_context

    return dev_user_context()


def test_validate_valid_xml(client: TestClient):
    schema_id = _upload_fixture(client)
    schema = dtd_routes._user_registry(_dev_user())[schema_id]
    xml_text = build_xml(schema, BuildConfig(root_element="PayDoc", mode="minimal")).xml_text

    response = client.post(
        "/api/validate",
        json={"schema_id": schema_id, "xml_text": xml_text},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["errors"] == []


def test_validate_invalid_xml(client: TestClient):
    schema_id = _upload_fixture(client)
    schema = dtd_routes._user_registry(_dev_user())[schema_id]
    xml_text = build_xml(schema, BuildConfig(root_element="PayDoc", mode="minimal")).xml_text
    bad_xml = xml_text.replace('id="', 'removed="', 1)

    response = client.post(
        "/api/validate",
        json={"schema_id": schema_id, "xml_text": bad_xml},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert len(data["errors"]) >= 1


def test_validate_schema_not_found(client: TestClient):
    response = client.post(
        "/api/validate",
        json={"schema_id": "missing", "xml_text": "<root/>"},
    )
    assert response.status_code == 404


def test_validate_uses_merged_schemas_from_registry(client: TestClient):
    from app.config import shared_dtd_dir

    dtd_dir = shared_dtd_dir()
    dtd_dir.mkdir(parents=True, exist_ok=True)

    uploads = [
        ("root.dtd", b'<!ELEMENT Root (add-object)>\n<!ATTLIST Root id ID #REQUIRED>\n'),
        (
            "cs.dtd",
            b'<!ELEMENT add-object (add-field*)>\n'
            b'<!ATTLIST add-object name CDATA #REQUIRED>\n'
            b'<!ELEMENT add-field EMPTY>\n',
        ),
    ]
    files = [("files", (name, content, "application/xml-dtd")) for name, content in uploads]
    upload_response = client.post("/api/dtd/upload", files=files)
    assert upload_response.status_code == 200
    schema_id = upload_response.json()["primary_schema_id"]

    xml_text = '<Root id="doc-1"><add-object name="obj"><add-field/></add-object></Root>'
    response = client.post(
        "/api/validate",
        json={"schema_id": schema_id, "xml_text": xml_text},
    )

    assert response.status_code == 200
    assert response.json()["valid"] is True


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
