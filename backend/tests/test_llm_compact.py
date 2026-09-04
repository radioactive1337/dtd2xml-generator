"""Tests for compact LLM fill task collection and value application."""

from lxml import etree

from app.core.dtd_models import AttributeDef, ContentNode, DTDSchema, ElementDef
from app.services.llm_service import (
    annotate_repeat_counts,
    apply_llm_values,
    build_batch_xml_skeleton,
    build_diversity_note,
    collect_fill_tasks,
    group_tasks_into_batches,
    parse_batch_xml_response,
)


def _paydoc_schema() -> DTDSchema:
    return DTDSchema(
        elements={
            "PayDoc": ElementDef(
                name="PayDoc",
                content_raw="(Body)",
                content_model=ContentNode(kind="SEQUENCE", children=[ContentNode(kind="REF", ref="Body")]),
                attributes={
                    "id": AttributeDef(name="id", attr_type="ID", default_decl="#REQUIRED"),
                    "kladr": AttributeDef(name="kladr", attr_type="CDATA", default_decl="#IMPLIED"),
                    "active": AttributeDef(name="active", attr_type="CDATA", default_decl="#IMPLIED"),
                },
            ),
            "Body": ElementDef(
                name="Body",
                content_raw="(Record)",
                content_model=ContentNode(kind="SEQUENCE", children=[ContentNode(kind="REF", ref="Record")]),
                attributes={},
            ),
            "Record": ElementDef(
                name="Record",
                content_raw="(Field)",
                content_model=ContentNode(kind="SEQUENCE", children=[ContentNode(kind="REF", ref="Field")]),
                attributes={},
            ),
            "Field": ElementDef(
                name="Field",
                content_raw="#PCDATA",
                content_model=ContentNode(kind="PCDATA"),
                attributes={
                    "name": AttributeDef(name="name", attr_type="CDATA", default_decl="#IMPLIED"),
                    "type": AttributeDef(
                        name="type",
                        attr_type="ENUM",
                        default_decl="#REQUIRED",
                        allowed_values=["string", "number"],
                    ),
                },
            ),
        }
    )


def test_collect_fill_tasks_hybrid_only_empty_and_placeholders():
    xml = (
        '<PayDoc id="id-1" kladr="from-db" active="true">'
        "<Body><Record><Field name=\"\" type=\"string\"/></Record></Body>"
        "</PayDoc>"
    )
    protected = frozenset({((), "kladr")})

    tasks = collect_fill_tasks(
        xml,
        _paydoc_schema(),
        fill_empty_only=True,
        protected_attrs=protected,
    )

    assert len(tasks) == 2
    assert tasks[0] == {"i": 0, "p": "PayDoc", "a": ["id"]}
    assert tasks[1] == {
        "i": 1,
        "p": "PayDoc.Body.Record.Field",
        "a": ["name"],
    }


def test_apply_llm_values_preserves_structure_and_db_values():
    original = (
        '<PayDoc id="id-1" kladr="from-db" active="true">'
        "<Body><Record><Field name=\"\" type=\"string\"/></Record></Body>"
        "</PayDoc>"
    )
    tasks = collect_fill_tasks(
        original,
        _paydoc_schema(),
        fill_empty_only=True,
        protected_attrs=frozenset({((), "kladr")}),
    )
    values = [
        {"i": 0, "a": {"id": "ai-id", "kladr": "999", "active": "false"}},
        {"i": 1, "a": {"name": "filled", "type": "number"}},
        {"i": 99, "a": {"x": "y"}},
    ]
    protected = frozenset({((), "kladr")})

    result = apply_llm_values(
        original,
        values,
        tasks=tasks,
        fill_empty_only=True,
        protected_attrs=protected,
    )

    assert 'id="ai-id"' in result
    assert 'kladr="from-db"' in result
    assert 'active="true"' in result
    assert 'name="filled"' in result
    assert 'type="string"' in result
    assert "Extra" not in result


def test_apply_llm_values_does_not_add_text_to_empty_element():
    schema = DTDSchema(
        elements={
            "saldo-incoming": ElementDef(
                name="saldo-incoming",
                content_raw="EMPTY",
                content_model=ContentNode(kind="EMPTY"),
                attributes={
                    "currency": AttributeDef(
                        name="currency", attr_type="CDATA", default_decl="#IMPLIED"
                    ),
                    "value": AttributeDef(name="value", attr_type="CDATA", default_decl="#IMPLIED"),
                },
            )
        }
    )
    original = '<saldo-incoming currency="" value=""/>'
    tasks = [{"i": 0, "p": "saldo-incoming", "a": ["currency", "value"]}]
    values = [
        {"i": 0, "a": {"currency": "RUB", "value": "150000.00", "extra": "nope"}, "t": "850000.00"}
    ]

    result = apply_llm_values(original, values, tasks=tasks, schema=schema)
    root = etree.fromstring(result.encode("utf-8"))

    assert root.get("currency") == "RUB"
    assert root.get("value") == "150000.00"
    assert "extra" not in root.attrib
    assert not (root.text or "").strip()


def test_apply_llm_values_fills_requested_pcdata():
    original = "<Field/>"
    schema = DTDSchema(
        elements={
            "Field": ElementDef(
                name="Field",
                content_raw="#PCDATA",
                content_model=ContentNode(kind="PCDATA"),
                attributes={},
            )
        }
    )
    tasks = [{"i": 0, "p": "Field", "t": 1}]
    values = [{"i": 0, "t": "hello"}]

    result = apply_llm_values(original, values, tasks=tasks, schema=schema)
    root = etree.fromstring(result.encode("utf-8"))
    assert (root.text or "").strip() == "hello"


def test_collect_fill_tasks_full_mode_includes_all_attributes():
    xml = '<PayDoc id="existing" kladr="" active="false"/>'

    tasks = collect_fill_tasks(xml, _paydoc_schema(), fill_empty_only=False)

    assert len(tasks) == 1
    assert tasks[0] == {
        "i": 0,
        "p": "PayDoc",
        "a": ["id", "kladr", "active"],
    }


def test_build_batch_xml_skeleton_and_parse_response():
    batch = [
        {"i": 0, "p": "PayDoc", "a": ["id"]},
        {"i": 1, "p": "PayDoc.Body.Record.Field", "a": ["name", "type"]},
    ]
    skeleton = build_batch_xml_skeleton(batch)
    assert '<f i="0" p="PayDoc" id=""/>' in skeleton
    assert '<f i="1" p="PayDoc.Body.Record.Field" name="" type=""/>' in skeleton

    filled = (
        "<fill>"
        '<f i="0" p="PayDoc" id="ai-id"/>'
        '<f i="1" p="PayDoc.Body.Record.Field" name="filled" type="string"/>'
        "</fill>"
    )
    values = parse_batch_xml_response(filled, batch)
    assert values == [
        {"i": 0, "a": {"id": "ai-id"}},
        {"i": 1, "a": {"name": "filled", "type": "string"}},
    ]


def test_parse_batch_ignores_unsolicited_text_on_attribute_tasks():
    batch = [{"i": 0, "p": "saldo-incoming", "a": ["value"]}]
    filled = '<fill><f i="0" p="saldo-incoming" value="150000.00">850000.00</f></fill>'
    assert parse_batch_xml_response(filled, batch) == [{"i": 0, "a": {"value": "150000.00"}}]


def test_parse_batch_keeps_text_when_requested():
    batch = [{"i": 0, "p": "Title", "t": 1}]
    filled = '<fill><f i="0" p="Title">Hello</f></fill>'
    assert parse_batch_xml_response(filled, batch) == [{"i": 0, "t": "Hello"}]


def test_parse_batch_ignores_copied_instance_index():
    batch = [{"i": 0, "p": "PayDoc.bank", "a": ["name"], "n": 1, "m": 2}]
    filled = '<fill><f i="0" p="PayDoc.bank" n="1/2" name="Сбербанк"/></fill>'
    assert parse_batch_xml_response(filled, batch) == [{"i": 0, "a": {"name": "Сбербанк"}}]


def _abt_account_tasks(account_index: int, start_i: int) -> list[dict]:
    prefix = f"abt-accounts.abt-account[{account_index}]"
    paths = [
        prefix,
        f"{prefix}.account",
        f"{prefix}.account.bank",
        f"{prefix}.account.bank.address",
        f"{prefix}.account.bank.contact[0]",
        f"{prefix}.account.bank.contact[1]",
        f"{prefix}.account.bank.contact[2]",
        f"{prefix}.account.bank.chief",
        f"{prefix}.account.bank.chief.identity-card",
        f"{prefix}.account.bank.chief-accountant",
        f"{prefix}.account.bank.chief-accountant.identity-card",
        f"{prefix}.account.bank.cr-info",
    ]
    return [
        {"i": start_i + offset, "p": path, "a": ["name"]}
        for offset, path in enumerate(paths)
    ]


def test_annotate_repeat_counts_and_skeleton_instance_index():
    tasks = _abt_account_tasks(0, 0) + _abt_account_tasks(1, 12) + _abt_account_tasks(2, 24)
    annotate_repeat_counts(tasks)

    banks = [task for task in tasks if task["p"].endswith(".bank")]
    assert [task["n"] for task in banks] == [1, 2, 3]
    assert all(task["m"] == 3 for task in banks)

    contacts = [task for task in tasks if ".contact[" in task["p"]]
    assert [task["n"] for task in contacts] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert all(task["m"] == 9 for task in contacts)

    skeleton = build_batch_xml_skeleton(banks)
    assert 'n="1/3"' in skeleton
    assert 'n="2/3"' in skeleton
    assert 'n="3/3"' in skeleton


def test_group_tasks_packs_sibling_accounts_into_one_batch():
    tasks = _abt_account_tasks(0, 0) + _abt_account_tasks(1, 12) + _abt_account_tasks(2, 24)
    batches = group_tasks_into_batches(tasks, batch_size=36, batch_max=48)

    assert len(batches) == 1
    assert [task["p"] for task in batches[0]] == [task["p"] for task in tasks]


def test_group_tasks_does_not_split_an_account_across_batches():
    tasks = _abt_account_tasks(0, 0) + _abt_account_tasks(1, 12)
    batches = group_tasks_into_batches(tasks, batch_size=18, batch_max=48)

    assert len(batches) == 2
    assert all(task["p"].startswith("abt-accounts.abt-account[0]") for task in batches[0])
    assert all(task["p"].startswith("abt-accounts.abt-account[1]") for task in batches[1])


def test_diversity_note_lists_repeated_tags():
    tasks = _abt_account_tasks(0, 0) + _abt_account_tasks(1, 12)
    annotate_repeat_counts(tasks)
    note = build_diversity_note(tasks)

    assert "bank: 1/2, 2/2" in note
    assert "contact: 1/6, 2/6, 3/6, 4/6, 5/6, 6/6" in note
    assert "identifying values MUST differ" in note


def test_diversity_note_empty_when_no_repeats():
    tasks = [{"i": 0, "p": "PayDoc", "a": ["id"]}]
    annotate_repeat_counts(tasks)
    assert build_diversity_note(tasks) == ""
    assert "n=" not in build_batch_xml_skeleton(tasks)
