"""Tests for peer XML sharing between users."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.users import get_user_by_norm, normalize_username
from app.user_context import user_context_from_record

SAMPLE_PERSONAL = {
    "name": "Мой тест",
    "schema_id": "schema-1",
    "category": "free-document",
    "description": "test doc",
    "xml_text": "<root>personal</root>",
}


def _save_personal(client: TestClient, payload: dict | None = None) -> dict:
    body = payload or SAMPLE_PERSONAL
    response = client.post("/api/xml-library/personal", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _user_ctx(username: str):
    record = get_user_by_norm(normalize_username(username))
    assert record is not None
    return user_context_from_record(record)


def test_share_personal_document_success(
    user_a_client: TestClient,
    user_b_client: TestClient,
):
    _save_personal(user_a_client)

    response = user_a_client.post(
        "/api/xml-library/share",
        json={
            "recipient_username": "bob",
            "source_document_name": "Мой тест",
            "message": "Для проверки",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["recipient_display_name"] == "bob"
    assert data["document_name"] == "Мой тест"

    bob_docs = user_b_client.get("/api/xml-library/personal").json()
    assert len(bob_docs) == 1
    assert bob_docs[0]["name"] == "Мой тест"
    assert bob_docs[0]["shared_by_name"] == "alice"
    assert bob_docs[0]["shared_at"]

    loaded = user_b_client.get("/api/xml-library/personal/Мой%20тест").json()
    assert loaded["xml_text"] == "<root>personal</root>"
    assert loaded["shared_by_name"] == "alice"
    assert "Для проверки" in loaded["description"]

    alice_docs = user_a_client.get("/api/xml-library/personal").json()
    assert len(alice_docs) == 1


def test_share_inline_document(
    user_a_client: TestClient,
    user_b_client: TestClient,
):
    response = user_a_client.post(
        "/api/xml-library/share",
        json={
            "recipient_username": "bob",
            "document": {
                "name": "Из редактора",
                "schema_id": "schema-2",
                "description": "inline",
                "xml_text": "<root>inline</root>",
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["document_name"] == "Из редактора"

    loaded = user_b_client.get("/api/xml-library/personal/Из%20редактора").json()
    assert loaded["xml_text"] == "<root>inline</root>"
    assert loaded["shared_by_name"] == "alice"


def test_share_source_not_found(user_a_client: TestClient, user_b_client: TestClient):
    response = user_a_client.post(
        "/api/xml-library/share",
        json={
            "recipient_username": "bob",
            "source_document_name": "missing",
        },
    )
    assert response.status_code == 404


def test_share_recipient_not_found(user_a_client: TestClient):
    _save_personal(user_a_client)
    response = user_a_client.post(
        "/api/xml-library/share",
        json={
            "recipient_username": "nobody",
            "source_document_name": "Мой тест",
        },
    )
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["message"] == "User 'nobody' not found"


def test_share_to_self(user_a_client: TestClient):
    _save_personal(user_a_client)
    response = user_a_client.post(
        "/api/xml-library/share",
        json={
            "recipient_username": "alice",
            "source_document_name": "Мой тест",
        },
    )
    assert response.status_code == 400
    assert "yourself" in response.json()["detail"].lower()


def test_share_name_conflict_resolution(
    user_a_client: TestClient,
    user_b_client: TestClient,
):
    _save_personal(user_b_client, {**SAMPLE_PERSONAL, "name": "Мой тест"})
    _save_personal(user_a_client)

    response = user_a_client.post(
        "/api/xml-library/share",
        json={
            "recipient_username": "bob",
            "source_document_name": "Мой тест",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["document_name"] == "Мой тест (от alice)"

    response = user_a_client.post(
        "/api/xml-library/share",
        json={
            "recipient_username": "bob",
            "source_document_name": "Мой тест",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["document_name"] == "Мой тест (от alice) (2)"


def test_share_missing_payload(user_a_client: TestClient, user_b_client: TestClient):
    response = user_a_client.post(
        "/api/xml-library/share",
        json={"recipient_username": "bob"},
    )
    assert response.status_code == 400
