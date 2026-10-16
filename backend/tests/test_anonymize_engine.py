"""Anonymization engine: classification, replacement, sweep, serialization."""

from __future__ import annotations

import pytest
from lxml import etree

from app.services.anonymize.engine import (
    AnonymizeError,
    Options,
    Override,
    analyze_document,
    apply_anonymization,
    collect_free_text,
)
from app.services.anonymize.generators import (
    inn12_checks,
    is_valid_inn,
)
from app.services.anonymize.rules import AnonRule, RuleSet, load_global_rules

KEY = b"k" * 32
INN = "5001007322" + inn12_checks("5001007322")


def _rules(*extra: AnonRule) -> RuleSet:
    return RuleSet([*load_global_rules(), *extra])


def _opts(**kwargs) -> Options:
    return Options(key=KEY, **kwargs)


def _attr_rule(attr: str, category: str, **kwargs) -> AnonRule:
    return AnonRule(attr=attr, action="replace", category=category, **kwargs)


DOC = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE Doc SYSTEM "doc.dtd">
<!-- реальный клиент Иванов Иван Иванович -->
<Doc xmlns:cs="http://example.com/cs">
  <!-- внутренний комментарий: Иванов -->
  <client inn="{INN}" status="NEW" fio="Иванов Иван Иванович"
          note="Заявку подал Иванов И.И. по телефону 8 916 123 45 67, почта ivanov@mail.ru, паспорт 4510 654321"/>
  <identity-card series="4510" number="654321"/>
  <cs:attribute name="LastName" value="Иванов"/>
  <cs:attribute name="Inn" value="{INN}"/>
  <cs:attribute name="IdentStage" value="full"/>
  <cs:attribute name="Mystery" value="Секретное значение клиента"/>
</Doc>
"""


def _apply(xml: str = DOC, **opt_kwargs):
    rules = _rules(_attr_rule("fio", "person_full"))
    return apply_anonymization(xml, rules, _opts(**opt_kwargs))


def _root(result) -> etree._Element:
    return etree.fromstring(result.body_text.encode("utf-8"))


def test_replaces_classified_values_and_keeps_structure():
    result = _apply()
    root = _root(result)
    client = root.find("client")
    assert client is not None

    assert client.get("inn") != INN
    assert is_valid_inn(client.get("inn"))
    assert len(client.get("inn")) == 12
    assert client.get("status") == "NEW"
    assert client.get("fio") != "Иванов Иван Иванович"
    assert "Иван" not in result.xml_text.replace("Иванов", "")  # no leftover first name


def test_cs_pairs_use_name_to_classify():
    result = _apply()
    root = _root(result)
    ns = {"cs": "http://example.com/cs"}
    pairs = {
        el.get("name"): el.get("value") for el in root.findall("cs:attribute", ns)
    }
    assert set(pairs) == {"LastName", "Inn", "IdentStage", "Mystery"}  # keys untouched
    assert pairs["LastName"] != "Иванов"
    assert pairs["Inn"] != INN and is_valid_inn(pairs["Inn"])
    assert pairs["IdentStage"] == "full"  # keep rule
    assert pairs["Mystery"] == "Секретное значение клиента"  # unclassified: left as is


def test_consistency_same_original_same_fake():
    result = _apply()
    root = _root(result)
    ns = {"cs": "http://example.com/cs"}
    inn_attr = root.find("client").get("inn")
    inn_pair = next(
        el.get("value") for el in root.findall("cs:attribute", ns) if el.get("name") == "Inn"
    )
    assert inn_attr == inn_pair


def test_sweep_cleans_free_text_consistently():
    result = _apply()
    root = _root(result)
    client = root.find("client")
    note = client.get("note")
    fio = client.get("fio").split()
    ident = root.find("identity-card")

    assert "Иванов" not in note
    assert "ivanov@mail.ru" not in note and "@example.com" in note
    assert "916 123 45 67" not in note
    assert "654321" not in note
    assert ident.get("number") in note
    # "Иванов И.И." -> "<fake last> <F>.<M>." following the full-name replacement
    assert f"{fio[0]} {fio[1][0]}.{fio[2][0]}." in note


def test_comments_removed_by_default_and_counted():
    result = _apply()
    assert "<!--" not in result.xml_text
    assert "Иванов Иван Иванович" not in result.xml_text
    assert result.report["comments_removed"] == 2


def test_comments_scrubbed_when_kept():
    result = _apply(strip_comments=False)
    assert "<!--" in result.xml_text
    assert "внутренний комментарий" in result.xml_text
    assert "Иванов" not in result.xml_text
    assert result.report["comments_removed"] == 0


def test_declaration_and_doctype_preserved():
    result = _apply()
    assert result.xml_text.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert '<!DOCTYPE Doc SYSTEM "doc.dtd">' in result.xml_text
    assert result.body_text.startswith('<!DOCTYPE Doc SYSTEM "doc.dtd">')
    etree.fromstring(result.body_text.encode("utf-8"))  # still well-formed


def test_unclassified_queue_and_status():
    result = _apply()
    report = result.report
    keys = {item["key"]: item for item in report["unclassified"]}

    assert "cs:attribute|value|Mystery" in keys
    assert keys["cs:attribute|value|Mystery"]["suspicious"] is True
    assert report["status"] == "needs_review"
    # classified or kept fields never reach the queue
    assert "cs:attribute|value|Inn" not in keys
    assert "cs:attribute|name|" not in {k for k in keys}
    assert all("Секретное" not in s for i in report["unclassified"] for s in i["samples"])


def test_override_resolves_queue_item():
    result = _apply(overrides={"cs:attribute|value|Mystery": Override(action="keep")})
    keys = {item["key"] for item in result.report["unclassified"]}
    assert "cs:attribute|value|Mystery" not in keys
    assert result.report["status"] in ("clean", "needs_review")


def test_override_replace_with_category():
    result = _apply(
        overrides={"cs:attribute|value|Mystery": Override(action="replace", category="format_preserving")}
    )
    root = _root(result)
    ns = {"cs": "http://example.com/cs"}
    mystery = next(
        el.get("value") for el in root.findall("cs:attribute", ns) if el.get("name") == "Mystery"
    )
    assert mystery != "Секретное значение клиента"
    assert len(mystery) == len("Секретное значение клиента")


def test_disabled_category_is_left_alone():
    result = _apply(enabled_categories=frozenset({"inn"}))
    root = _root(result)
    ns = {"cs": "http://example.com/cs"}
    last = next(
        el.get("value") for el in root.findall("cs:attribute", ns) if el.get("name") == "LastName"
    )
    assert last == "Иванов"  # person_last disabled
    assert root.find("client").get("inn") != INN  # inn enabled


def test_deterministic_for_same_key():
    assert _apply().xml_text == _apply().xml_text


def test_different_key_changes_output():
    rules = _rules(_attr_rule("fio", "person_full"))
    a = apply_anonymization(DOC, rules, Options(key=b"a" * 32))
    b = apply_anonymization(DOC, rules, Options(key=b"b" * 32))
    assert a.xml_text != b.xml_text


def test_analyze_masks_values_and_reports_stats():
    rules = _rules(_attr_rule("fio", "person_full"))
    analysis = analyze_document(DOC, rules, _opts())
    assert analysis.stats["replace"] >= 5
    assert analysis.stats["unclassified"] >= 1
    for finding in analysis.findings:
        assert "Иванов Иван Иванович" != finding["masked_preview"]
        assert INN not in finding["masked_preview"]
    assert any(f["category"] == "inn" for f in analysis.findings)


def test_not_well_formed_raises():
    with pytest.raises(AnonymizeError):
        apply_anonymization("<a><b></a>", _rules(), _opts())


def test_empty_raises():
    with pytest.raises(AnonymizeError):
        apply_anonymization("   ", _rules(), _opts())


def test_external_entity_is_not_resolved(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-CONTENT", encoding="utf-8")
    xml = (
        f'<!DOCTYPE a [<!ENTITY xxe SYSTEM "{secret.as_uri()}">]>'
        '<a><v>&xxe;</v></a>'
    )
    result = apply_anonymization(xml, _rules(), _opts())
    assert "TOP-SECRET-CONTENT" not in result.xml_text
    assert "&xxe;" in result.xml_text


def test_text_nodes_are_classified_by_text_rule():
    xml = "<Doc><Phone>+7 (916) 111-22-33</Phone><Other>Привет мир</Other></Doc>"
    rules = _rules(AnonRule(element="Phone", attr="#text", action="replace", category="phone"))
    result = apply_anonymization(xml, rules, _opts())
    root = _root(result)
    assert root.find("Phone").text != "+7 (916) 111-22-33"
    assert root.find("Phone").text.startswith("+7 (")
    assert root.find("Other").text == "Привет мир"
    assert {i["key"] for i in result.report["unclassified"]} == {"Other|#text|"}


def test_free_text_category_scans_for_known_values():
    xml = (
        '<Doc><client fio="Петров Пётр Петрович"/>'
        '<note>Клиент Петров Пётр Петрович просил перезвонить</note></Doc>'
    )
    rules = _rules(
        _attr_rule("fio", "person_full"),
        AnonRule(element="note", attr="#text", action="replace", category="free_text"),
    )
    result = apply_anonymization(xml, rules, _opts())
    root = _root(result)
    assert "Петров" not in result.xml_text
    fio = root.find("client").get("fio")
    assert fio in root.find("note").text


def test_extra_entities_from_llm_are_replaced_everywhere_in_free_text():
    xml = '<Doc><note>Передать документы Сидорову Алексею лично</note></Doc>'
    rules = _rules(AnonRule(element="note", attr="#text", action="replace", category="free_text"))
    result = apply_anonymization(
        xml, rules, _opts(extra_entities=[("Сидорову Алексею", "person_full")])
    )
    assert "Сидорову" not in result.xml_text


def test_collect_free_text_picks_long_suspicious_values_and_free_text_slots():
    xml = (
        '<Doc><note>Передать документы Сидорову Алексею лично завтра</note>'
        '<code>AB</code></Doc>'
    )
    rules = _rules()
    texts = collect_free_text(xml, rules, _opts())
    assert texts == ["Передать документы Сидорову Алексею лично завтра"]


def test_leak_check_flags_kept_field_with_replaced_value():
    xml = '<Doc><client inn="%s"/><debug note="inn %s"/></Doc>' % (INN, INN)
    rules = _rules(AnonRule(element="debug", attr="note", action="keep"))
    result = apply_anonymization(xml, rules, _opts())
    assert result.report["leak_check"]["ok"] is False
    assert result.report["leak_check"]["items"][0]["attr"] == "note"


def test_account_key_valid_for_replaced_bic_in_same_element():
    from app.services.anonymize.generators import is_valid_account

    xml = '<Doc><bank bic="044525225" account-number="40702810099910004312"/></Doc>'
    result = apply_anonymization(xml, _rules(), _opts())
    bank = _root(result).find("bank")
    assert bank.get("bic") != "044525225"
    assert is_valid_account(bank.get("bic"), bank.get("account-number"))
