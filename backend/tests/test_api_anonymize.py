"""HTTP API for anonymization: analyze, apply, rules, LLM assist."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.anonymize import llm_assist
from app.services.anonymize import rules as anon_rules
from app.services.anonymize.generators import inn12_checks, is_valid_inn

INN = "5001007322" + inn12_checks("5001007322")

XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<Doc xmlns:cs="http://example.com/cs">
  <client inn="{INN}" fio="Иванов Иван Иванович" status="NEW"/>
  <cs:attribute name="LastName" value="Иванов"/>
  <cs:attribute name="Mystery" value="Секретное значение клиента"/>
  <note>Передать документы Сидорову Алексею лично завтра</note>
</Doc>
"""


@pytest.fixture(autouse=True)
def _isolated_global_rules(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Use a tiny global file so tests do not depend on the shipped starter set."""
    path = tmp_path / "anonymize_rules.json"
    path.write_text(
        """{"version":1,"rules":[
        {"id":"t-inn","attr":"inn","action":"replace","category":"inn"},
        {"id":"t-last","element":"cs:attribute","attr":"value","name":"LastName","action":"replace","category":"person_last"},
        {"id":"t-keep-name","element":"cs:attribute","attr":"name","action":"keep"},
        {"id":"t-status","attr":"status","action":"keep"}
        ]}""",
        encoding="utf-8",
    )
    monkeypatch.setattr(anon_rules, "ANON_RULES_FILE", path)
    monkeypatch.setattr(anon_rules, "ANON_RULES_EXAMPLE", tmp_path / "missing.example")
    anon_rules.clear_global_rules_cache()
    yield
    anon_rules.clear_global_rules_cache()


def _unclassified_keys(payload: dict) -> set[str]:
    return {item["key"] for item in payload["unclassified"]}


def test_categories_listed(client: TestClient):
    response = client.get("/api/anonymize/categories")
    assert response.status_code == 200
    ids = {c["id"] for c in response.json()["categories"]}
    assert {"inn", "person_full", "snils", "free_text"} <= ids


def test_analyze_does_not_return_real_values(client: TestClient):
    response = client.post("/api/anonymize/analyze", json={"xml_text": XML})
    assert response.status_code == 200
    body = response.json()

    assert body["root_element"] == "Doc"
    assert body["stats"]["replace"] == 2
    assert "cs:attribute|value|Mystery" in _unclassified_keys(body)
    raw = response.text
    assert INN not in raw
    assert "Иванов Иван" not in raw
    assert "Секретное значение клиента" not in raw


def test_analyze_rejects_bad_xml(client: TestClient):
    response = client.post("/api/anonymize/analyze", json={"xml_text": "<a><b></a>"})
    assert response.status_code == 400


def test_apply_replaces_and_reports(client: TestClient):
    response = client.post("/api/anonymize/apply", json={"xml_text": XML})
    assert response.status_code == 200
    data = response.json()
    result = data["xml_text"]
    report = data["report"]

    assert INN not in result
    assert result.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert report["replaced"] == 2
    assert report["status"] == "needs_review"
    assert report["unresolved_suspicious"] >= 1
    assert report["consistency"] == "document"
    assert any(row["category"] == "inn" for row in report["by_category"])
    assert 'status="NEW"' in result
    # the original document is not cached for the fill pipeline
    assert "Секретное" in result  # unclassified value is untouched


def test_apply_user_consistency_is_stable_across_requests(client: TestClient):
    payload = {"xml_text": XML, "consistency": "user"}
    first = client.post("/api/anonymize/apply", json=payload).json()["xml_text"]
    second = client.post("/api/anonymize/apply", json=payload).json()["xml_text"]
    assert first == second


def test_apply_document_consistency_differs_between_runs(client: TestClient):
    first = client.post("/api/anonymize/apply", json={"xml_text": XML}).json()["xml_text"]
    second = client.post("/api/anonymize/apply", json={"xml_text": XML}).json()["xml_text"]
    assert first != second


def test_apply_project_seed_is_shared_and_required(client: TestClient):
    missing = client.post(
        "/api/anonymize/apply", json={"xml_text": XML, "consistency": "project"}
    )
    assert missing.status_code == 400

    payload = {"xml_text": XML, "consistency": "project", "seed": "sprint-42"}
    a = client.post("/api/anonymize/apply", json=payload).json()["xml_text"]
    b = client.post("/api/anonymize/apply", json=payload).json()["xml_text"]
    c = client.post(
        "/api/anonymize/apply", json={**payload, "seed": "sprint-43"}
    ).json()["xml_text"]
    assert a == b and a != c


def test_apply_overrides_and_category_filter(client: TestClient):
    response = client.post(
        "/api/anonymize/apply",
        json={
            "xml_text": XML,
            "overrides": [{"key": "cs:attribute|value|Mystery", "action": "keep"}],
            "categories": ["inn"],
        },
    )
    assert response.status_code == 200
    report = response.json()["report"]
    assert "cs:attribute|value|Mystery" not in {i["key"] for i in report["unclassified"]}
    assert report["replaced"] == 1  # person_last category disabled

    bad = client.post(
        "/api/anonymize/apply", json={"xml_text": XML, "categories": ["nope"]}
    )
    assert bad.status_code == 400


def test_apply_override_replace_requires_category(client: TestClient):
    response = client.post(
        "/api/anonymize/apply",
        json={"xml_text": XML, "overrides": [{"key": "a|b|", "action": "replace"}]},
    )
    assert response.status_code == 400


def test_apply_with_dtd_validation(client: TestClient):
    from app.api.routes import dtd as dtd_routes
    from app.core.dtd_parser import DTDParser

    schema = DTDParser().parse_string(
        "<!ELEMENT Doc (client)>\n"
        "<!ELEMENT client EMPTY>\n"
        "<!ATTLIST client inn CDATA #REQUIRED fio CDATA #IMPLIED status CDATA #IMPLIED>\n"
    )
    dtd_routes._schema_registry["main"] = schema
    xml = f'<Doc><client inn="{INN}" fio="Иванов Иван Иванович" status="NEW"/></Doc>'

    response = client.post(
        "/api/anonymize/apply", json={"xml_text": xml, "schema_id": "main"}
    )
    assert response.status_code == 200, response.text
    validation = response.json()["report"]["validation"]
    assert validation["dtd"]["valid_after"] is True
    assert validation["rules"]["new_errors"] == []


def test_rules_crud_and_effect_on_queue(client: TestClient):
    rules = client.get("/api/anonymize/rules").json()
    assert {r["id"] for r in rules["global"]} >= {"t-inn", "t-last"}
    assert rules["user"] == []

    created = client.post(
        "/api/anonymize/rules/upsert",
        json={
            "rules": [
                {
                    "element": "cs:attribute",
                    "attr": "value",
                    "name": "Mystery",
                    "action": "replace",
                    "category": "format_preserving",
                    "source": "manual",
                }
            ]
        },
    )
    assert created.status_code == 200
    user_rules = created.json()["user"]
    assert len(user_rules) == 1 and user_rules[0]["id"].startswith("u-")
    assert user_rules[0]["created_by"] == "dev"

    analyze = client.post("/api/anonymize/analyze", json={"xml_text": XML}).json()
    assert "cs:attribute|value|Mystery" not in _unclassified_keys(analyze)

    # upserting the same scope replaces instead of duplicating
    again = client.post(
        "/api/anonymize/rules/upsert",
        json={
            "rules": [
                {
                    "element": "cs:attribute",
                    "attr": "value",
                    "name": "Mystery",
                    "action": "keep",
                }
            ]
        },
    ).json()["user"]
    assert len(again) == 1 and again[0]["action"] == "keep"

    rule_id = again[0]["id"]
    assert client.delete(f"/api/anonymize/rules/{rule_id}").status_code == 200
    assert client.delete(f"/api/anonymize/rules/{rule_id}").status_code == 404
    assert client.get("/api/anonymize/rules").json()["user"] == []


def test_user_rule_overrides_global_on_tie(client: TestClient):
    client.post(
        "/api/anonymize/rules/upsert",
        json={"rules": [{"attr": "status", "action": "replace", "category": "format_preserving"}]},
    )
    result = client.post("/api/anonymize/apply", json={"xml_text": XML}).json()["xml_text"]
    assert 'status="NEW"' not in result


def test_rule_validation_rejects_unknown_category(client: TestClient):
    response = client.post(
        "/api/anonymize/rules/upsert",
        json={"rules": [{"attr": "x", "action": "replace", "category": "bogus"}]},
    )
    assert response.status_code == 422


def test_rules_export_import_roundtrip(client: TestClient):
    client.post(
        "/api/anonymize/rules/upsert",
        json={"rules": [{"attr": "foo", "action": "replace", "category": "phone"}]},
    )
    exported = client.get("/api/anonymize/rules/export").json()
    assert exported["version"] == 1 and len(exported["rules"]) == 1

    client.delete("/api/anonymize/rules")
    imported = client.post(
        "/api/anonymize/rules/import",
        json={
            "rules": [
                *exported["rules"],
                {"attr": "broken", "action": "replace", "category": "bogus"},
            ],
            "mode": "merge",
        },
    ).json()
    assert imported["imported"] == 1 and imported["skipped"] == 1
    assert [r["attr"] for r in imported["user"]] == ["foo"]


def test_user_rules_are_per_user(user_a_client: TestClient, user_b_client: TestClient):
    user_a_client.post(
        "/api/anonymize/rules/upsert",
        json={"rules": [{"attr": "foo", "action": "keep"}]},
    )
    assert len(user_a_client.get("/api/anonymize/rules").json()["user"]) == 1
    assert user_b_client.get("/api/anonymize/rules").json()["user"] == []


def test_xml_not_staged_in_server_cache(client: TestClient):
    from app.api.routes import generate as generate_routes

    client.post("/api/anonymize/apply", json={"xml_text": XML})
    assert not generate_routes._last_generated


# -- LLM ---------------------------------------------------------------------


def test_apply_with_llm_replaces_entities_in_free_text(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr("app.api.routes.anonymize.resolve_llm_alias", lambda _u, _a=None: "fake")

    async def fake_ask(_llm, _system, user_message):
        assert "Сидорову Алексею" in user_message
        entities = [
            {"text": "Сидорову Алексею", "type": "person"},
            {"text": "Несуществующий текст", "type": "person"},
        ]
        # Text order is an implementation detail; answer for every item and
        # rely on the engine dropping entities that are not in that text.
        return {"items": [{"i": i, "entities": entities} for i in range(10)]}

    monkeypatch.setattr(llm_assist, "_ask", fake_ask)
    response = client.post(
        "/api/anonymize/apply", json={"xml_text": XML, "use_llm": True, "llm_alias": "fake"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "Сидорову" not in data["xml_text"]
    llm = data["report"]["llm"]
    assert llm["used"] is True and llm["alias"] == "fake"
    assert llm["entities_found"] == 1  # the invented text was dropped


def test_apply_continues_when_llm_fails(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.api.routes.anonymize.resolve_llm_alias", lambda _u, _a=None: "fake")

    async def broken(*_a, **_k):
        raise ValueError("LLM request failed: boom")

    monkeypatch.setattr(llm_assist, "_ask", broken)
    response = client.post(
        "/api/anonymize/apply", json={"xml_text": XML, "use_llm": True}
    )
    assert response.status_code == 200
    report = response.json()["report"]
    assert any("ИИ не обработал" in w for w in report["warnings"])
    assert INN not in response.json()["xml_text"]


def test_apply_llm_without_alias_degrades_to_warning(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    def no_alias(_user, _alias=None):
        raise ValueError("No LLM aliases configured")

    monkeypatch.setattr("app.api.routes.anonymize.resolve_llm_alias", no_alias)
    response = client.post("/api/anonymize/apply", json={"xml_text": XML, "use_llm": True})
    assert response.status_code == 200
    report = response.json()["report"]
    assert report["llm"]["used"] is False
    assert any("ИИ-поиск пропущен" in w for w in report["warnings"])


def test_parse_entities_drops_text_not_in_source():
    data = {
        "items": [
            {"i": 0, "entities": [{"text": "Иван Петров", "type": "person"},
                                  {"text": "выдумка", "type": "person"},
                                  {"text": "Иван", "type": "unknown"}]},
            {"i": 7, "entities": [{"text": "x", "type": "person"}]},
            "garbage",
        ]
    }
    assert llm_assist.parse_entities(data, ["Звонил Иван Петров вчера"]) == [
        ("Иван Петров", "person_full")
    ]


def test_parse_entities_requires_items_array():
    with pytest.raises(ValueError):
        llm_assist.parse_entities({"nope": 1}, ["x"])


def test_parse_suggestions_filters_unknown():
    data = {
        "suggestions": [
            {"key": "a|b|", "category": "inn"},
            {"key": "c|d|", "category": "none"},
            {"key": "e|f|", "category": "bogus"},
            {"key": "zzz", "category": "inn"},
        ]
    }
    assert llm_assist.parse_suggestions(data, {"a|b|", "c|d|", "e|f|"}) == {
        "a|b|": "inn",
        "c|d|": None,
    }


def test_suggest_categories_for_items(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.api.routes.anonymize.resolve_llm_alias", lambda _u, _a=None: "fake")
    seen: dict[str, str] = {}

    async def fake_ask(_llm, _system, user_message):
        seen["message"] = user_message
        return {"suggestions": [{"key": "Client|taxId|", "category": "inn"}]}

    monkeypatch.setattr(llm_assist, "_ask", fake_ask)
    response = client.post(
        "/api/anonymize/suggest-categories",
        json={
            "items": [
                {"key": "Client|taxId|", "element": "Client", "attr": "taxId",
                 "doc": "Taxpayer id", "sample": "5001007322"}
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["suggestions"] == {"Client|taxId|": "inn"}
    assert "5001007322" not in seen["message"]  # samples are opt-in

    response = client.post(
        "/api/anonymize/suggest-categories",
        json={
            "items": [{"key": "Client|taxId|", "element": "Client", "attr": "taxId",
                       "sample": "5001007322"}],
            "include_samples": True,
        },
    )
    assert response.status_code == 200
    assert "5001007322" in seen["message"]


def test_suggest_categories_schema_mode_uses_cache(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from app.api.routes import dtd as dtd_routes
    from app.core.dtd_parser import DTDParser

    schema = DTDParser().parse_string(
        "<!ELEMENT Doc EMPTY>\n"
        "<!ATTLIST Doc taxId CDATA #IMPLIED color (red|blue) #IMPLIED inn CDATA #IMPLIED>\n"
    )
    dtd_routes._schema_registry["main"] = schema
    monkeypatch.setattr("app.api.routes.anonymize.resolve_llm_alias", lambda _u, _a=None: "fake")
    calls: list[str] = []

    async def fake_ask(_llm, _system, user_message):
        calls.append(user_message)
        return {"suggestions": [{"key": "Doc|taxId|", "category": "inn"}]}

    monkeypatch.setattr(llm_assist, "_ask", fake_ask)

    first = client.post("/api/anonymize/suggest-categories", json={"schema_id": "main"})
    assert first.status_code == 200
    # enum attr (color) and the already-ruled attr (inn) are not sent
    assert "Doc|taxId|" in calls[0]
    assert "color" not in calls[0] and "Doc|inn|" not in calls[0]
    assert first.json()["remaining"] == 0

    second = client.post("/api/anonymize/suggest-categories", json={"schema_id": "main"})
    assert second.json()["processed"] == 0
    assert len(calls) == 1  # cached, no second LLM call

    analyze = client.post(
        "/api/anonymize/analyze",
        json={"xml_text": '<Doc taxId="Секретный идентификатор клиента"/>', "schema_id": "main"},
    ).json()
    item = next(i for i in analyze["unclassified"] if i["key"] == "Doc|taxId|")
    assert item["llm_category"] == "inn"


def test_global_cs_inn_generates_valid_inn_through_api(client: TestClient):
    xml = f'<Doc xmlns:cs="http://example.com/cs"><cs:attribute name="x" value="{INN}"/><client inn="{INN}"/></Doc>'
    data = client.post("/api/anonymize/apply", json={"xml_text": xml}).json()
    import re

    inns = re.findall(r'inn="(\d+)"', data["xml_text"])
    assert inns and is_valid_inn(inns[0]) and inns[0] != INN
    # unclassified pair value holding the same number is swept to the same fake
    assert INN not in data["xml_text"]

