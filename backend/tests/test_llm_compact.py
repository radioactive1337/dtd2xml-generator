"""Tests for compact LLM fill task collection and value application."""

from app.core.dtd_models import AttributeDef, ContentNode, DTDSchema, ElementDef
from app.services.llm_service import (
    apply_llm_values,
    build_batch_xml_skeleton,
    collect_fill_tasks,
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
        "a": ["name", "type"],
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
