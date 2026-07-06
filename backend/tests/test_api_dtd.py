"""Tests for DTD API endpoints."""

from pathlib import Path

from fastapi.testclient import TestClient

FIXTURES = Path(__file__).parent / "fixtures"


def _seed_types_dtd() -> None:
    from app.user_context import dev_user_context

    dtd_dir = dev_user_context().dtd_dir
    dtd_dir.mkdir(parents=True, exist_ok=True)
    (dtd_dir / "types.dtd").write_bytes((FIXTURES / "types.dtd").read_bytes())


def test_health(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_config_aliases_no_secrets(client: TestClient):
    response = client.get("/api/config/aliases")
    assert response.status_code == 200
    data = response.json()
    assert "databases" in data
    assert "llm" in data
    assert "default_llm" in data


def test_upload_dtd(client: TestClient):
    _seed_types_dtd()
    dtd_path = FIXTURES / "main.dtd"
    with dtd_path.open("rb") as f:
        response = client.post(
            "/api/dtd/upload",
            files=[("files", ("main.dtd", f, "application/xml-dtd"))],
        )

    assert response.status_code == 200
    data = response.json()
    assert "primary_schema_id" in data
    assert len(data["schemas"]) == 1
    assert data["primary_schema_id"] == data["schemas"][0]["schema_id"]
    assert data["schemas"][0]["element_count"] > 0
    assert "PayDoc" in data["schemas"][0]["elements"]


def test_upload_multiple_dtd(client: TestClient, tmp_path):
    _seed_types_dtd()
    uploads = [
        ("v1.dtd", FIXTURES / "v1.dtd"),
        ("v2.dtd", FIXTURES / "v2.dtd"),
    ]
    files = []
    for name, path in uploads:
        files.append(("files", (name, path.open("rb"), "application/xml-dtd")))

    try:
        response = client.post("/api/dtd/upload", files=files)
    finally:
        for _, (_, handle, _) in files:
            handle.close()

    assert response.status_code == 200
    data = response.json()
    assert len(data["schemas"]) == 2
    roots = {tuple(schema["elements"]) for schema in data["schemas"]}
    assert ("Legacy",) in roots
    assert "PayDoc" in {element for schema in data["schemas"] for element in schema["elements"]}


def test_upload_more_than_three_dtd_rejected(client: TestClient):
    files = [
        ("files", (f"v{i}.dtd", (FIXTURES / "v1.dtd").open("rb"), "application/xml-dtd"))
        for i in range(4)
    ]
    try:
        response = client.post("/api/dtd/upload", files=files)
    finally:
        for _, (_, handle, _) in files:
            handle.close()

    assert response.status_code == 400


def test_list_schemas(client: TestClient):
    schema_id = _upload_fixture(client)

    response = client.get("/api/dtd/schemas")
    assert response.status_code == 200
    schemas = response.json()
    assert len(schemas) == 1
    assert schemas[0]["schema_id"] == schema_id
    assert schemas[0]["element_count"] > 0
    assert "PayDoc" in schemas[0]["elements"]


def test_list_elements(client: TestClient):
    schema_id = _upload_fixture(client)

    response = client.get(f"/api/dtd/{schema_id}/elements")
    assert response.status_code == 200
    elements = response.json()
    names = [e["name"] for e in elements]
    assert "PayDoc" in names
    paydoc = next(e for e in elements if e["name"] == "PayDoc")
    assert "Основной корневой элемент" in paydoc["doc"]
    assert paydoc["attribute_docs"].get("kladr") == "код КЛАДР"


def test_get_element_detail(client: TestClient):
    schema_id = _upload_fixture(client)

    response = client.get(f"/api/dtd/{schema_id}/elements/PayDoc")
    assert response.status_code == 200
    data = response.json()
    assert data["element"]["name"] == "PayDoc"
    assert "Основной корневой элемент" in data["element"]["doc"]
    assert "kladr" in data["element"]["required_attributes"]


def test_get_element_tree(client: TestClient):
    schema_id = _upload_fixture(client)

    response = client.get(f"/api/dtd/{schema_id}/elements/PayDoc/tree")
    assert response.status_code == 200
    data = response.json()
    assert data["element"] == "PayDoc"
    assert data["content_model"]["kind"] == "SEQUENCE"


def test_schema_not_found(client: TestClient):
    response = client.get("/api/dtd/nonexistent/elements")
    assert response.status_code == 404


def _upload_fixture(client: TestClient) -> str:
    _seed_types_dtd()
    dtd_path = FIXTURES / "main.dtd"
    with dtd_path.open("rb") as f:
        response = client.post(
            "/api/dtd/upload",
            files=[("files", ("main.dtd", f, "application/xml-dtd"))],
        )
    return response.json()["primary_schema_id"]
