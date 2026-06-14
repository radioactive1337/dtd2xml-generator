"""Tests for XML builder."""

from pathlib import Path

import pytest
from lxml import etree

from app.core.dtd_parser import DTDParser
from app.core.dtd_validator import validate_xml
from app.core.xml_builder import BuildConfig, build_xml

AUX_AUTH_DTD = """
<!ELEMENT root (aux-auth)>
<!ELEMENT aux-auth (auth-3ds?, mac-info?, (front-auth-key|front-auth-token)?)>
<!ELEMENT auth-3ds EMPTY>
<!ELEMENT mac-info EMPTY>
<!ELEMENT front-auth-key EMPTY>
<!ELEMENT front-auth-token EMPTY>
"""

CUSTOMER_DTD = """
<!ELEMENT customer ((person | corporation), legal-address?, postal-address?, contact*)>
<!ELEMENT person (identity-card?, key?)>
<!ATTLIST person name CDATA #IMPLIED>
<!ELEMENT corporation EMPTY>
<!ATTLIST corporation name CDATA #IMPLIED bic-type (ru|swift) "ru">
<!ELEMENT legal-address EMPTY>
<!ELEMENT postal-address EMPTY>
<!ELEMENT contact EMPTY>
<!ATTLIST contact type (email|phone) "email" value CDATA #IMPLIED is-corp (true|false) "false">
<!ELEMENT identity-card EMPTY>
<!ELEMENT key EMPTY>
"""

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def schema():
    parser = DTDParser(base_dir=FIXTURES)
    return parser.parse_file(FIXTURES / "main.dtd")


def test_minimal_build(schema):
    config = BuildConfig(
        root_element="PayDoc",
        mode="minimal",
    )
    result = build_xml(schema, config)
    root = etree.fromstring(result.xml_text.encode("utf-8"))

    assert root.tag == "PayDoc"
    assert "id" in root.attrib
    assert "kladr" in root.attrib
    assert "status" not in root.attrib  # implied, not in minimal

    children = [c.tag for c in root]
    assert "Header" in children
    assert "Body" in children
    assert "Footer" not in children  # optional ?


def test_maximal_build(schema):
    config = BuildConfig(
        root_element="PayDoc",
        mode="maximal",
        repeat_count=2,
    )
    result = build_xml(schema, config)
    root = etree.fromstring(result.xml_text.encode("utf-8"))

    assert "status" in root.attrib
    assert "Footer" in [c.tag for c in root]

    body = root.find("Body")
    assert body is not None
    records = body.findall("Record")
    assert len(records) == 2


def test_custom_build(schema):
    config = BuildConfig(
        root_element="PayDoc",
        mode="custom",
        custom_paths={"PayDoc.Footer", "PayDoc.Header.Meta"},
    )
    result = build_xml(schema, config)
    root = etree.fromstring(result.xml_text.encode("utf-8"))

    assert "Footer" in [c.tag for c in root]
    header = root.find("Header")
    assert header is not None
    assert len(header.findall("Meta")) >= 1


def test_custom_build_repeat_count(schema):
    config = BuildConfig(
        root_element="PayDoc",
        mode="custom",
        repeat_count=3,
        custom_paths={"PayDoc.Header.Meta"},
    )
    result = build_xml(schema, config)
    header = etree.fromstring(result.xml_text.encode("utf-8")).find("Header")

    assert header is not None
    assert len(header.findall("Meta")) == 3


def test_pcdata_element(schema):
    config = BuildConfig(root_element="Title", mode="minimal")
    result = build_xml(schema, config)
    root = etree.fromstring(result.xml_text.encode("utf-8"))
    assert root.tag == "Title"
    assert root.text in (None, "")


def test_empty_element(schema):
    config = BuildConfig(root_element="Footer", mode="minimal")
    result = build_xml(schema, config)
    root = etree.fromstring(result.xml_text.encode("utf-8"))
    assert root.tag == "Footer"
    assert len(root) == 0


@pytest.fixture
def aux_auth_schema():
    parser = DTDParser()
    return parser.parse_string(AUX_AUTH_DTD)


def test_custom_optional_choice_not_auto_included(aux_auth_schema):
    config = BuildConfig(
        root_element="root",
        mode="custom",
        custom_paths={"root.aux-auth"},
    )
    result = build_xml(aux_auth_schema, config)
    aux_auth = etree.fromstring(result.xml_text.encode("utf-8")).find("aux-auth")

    assert aux_auth is not None
    assert [c.tag for c in aux_auth] == []


def test_custom_optional_choice_includes_selected_branch(aux_auth_schema):
    config = BuildConfig(
        root_element="root",
        mode="custom",
        custom_paths={"root.aux-auth", "root.aux-auth.front-auth-key"},
    )
    result = build_xml(aux_auth_schema, config)
    aux_auth = etree.fromstring(result.xml_text.encode("utf-8")).find("aux-auth")

    assert aux_auth is not None
    assert [c.tag for c in aux_auth] == ["front-auth-key"]


def test_custom_choice_accepts_ui_group_path(aux_auth_schema):
    config = BuildConfig(
        root_element="root",
        mode="custom",
        custom_paths={"root.aux-auth", "root.aux-auth.group-2.front-auth-key"},
    )
    result = build_xml(aux_auth_schema, config)
    aux_auth = etree.fromstring(result.xml_text.encode("utf-8")).find("aux-auth")

    assert aux_auth is not None
    assert [c.tag for c in aux_auth] == ["front-auth-key"]


@pytest.fixture
def enterprise_schema():
    parser = DTDParser(base_dir=FIXTURES)
    return parser.parse_file(FIXTURES / "enterprise_sample.dtd")


def test_literal_default_attribute_in_skeleton(enterprise_schema):
    config = BuildConfig(root_element="success", mode="maximal")
    result = build_xml(enterprise_schema, config)
    root = etree.fromstring(result.xml_text.encode("utf-8"))
    assert root.attrib.get("document_type") == "a"


@pytest.fixture
def customer_schema():
    return DTDParser().parse_string(CUSTOMER_DTD)


def test_maximal_choice_picks_single_branch(customer_schema):
    config = BuildConfig(root_element="customer", mode="maximal")
    result = build_xml(customer_schema, config)
    root = etree.fromstring(result.xml_text.encode("utf-8"))

    assert "person" in [c.tag for c in root]
    assert "corporation" not in [c.tag for c in root]
    assert validate_xml(result.xml_text, customer_schema).valid


def test_maximal_optional_choice_validates(aux_auth_schema):
    config = BuildConfig(root_element="root", mode="maximal")
    result = build_xml(aux_auth_schema, config)
    aux_auth = etree.fromstring(result.xml_text.encode("utf-8")).find("aux-auth")

    assert aux_auth is not None
    auth_children = [c.tag for c in aux_auth if c.tag in ("front-auth-key", "front-auth-token")]
    assert len(auth_children) == 1
    assert validate_xml(result.xml_text, aux_auth_schema).valid


EMPLOYEE_CHOICE_DTD = """
<!ELEMENT root (worker)>
<!ELEMENT worker (((person, mgr?) | (idcard?, token?, mgr)), note?)>
<!ELEMENT person EMPTY>
<!ELEMENT mgr EMPTY>
<!ELEMENT idcard EMPTY>
<!ELEMENT token EMPTY>
<!ELEMENT note EMPTY>
"""


@pytest.fixture
def employee_choice_schema():
    return DTDParser().parse_string(EMPLOYEE_CHOICE_DTD)


def test_custom_nested_choice_picks_identity_branch(employee_choice_schema):
    """UI paths like root.worker.group-0.group-1 must not match the sibling group-0 branch."""
    config = BuildConfig(
        root_element="root",
        mode="custom",
        custom_paths={
            "root.worker.group-0.group-1",
            "root.worker.group-0.group-1.idcard",
            "root.worker.group-0.group-1.token",
            "root.worker.group-0.group-1.mgr",
        },
    )
    result = build_xml(employee_choice_schema, config)
    worker = etree.fromstring(result.xml_text.encode("utf-8")).find("worker")

    assert worker is not None
    assert worker.find("person") is None
    tags = [c.tag for c in worker]
    assert "idcard" in tags
    assert "token" in tags
    assert "mgr" in tags
    assert "person" not in tags


def test_maximal_build_validates_against_dtd(schema):
    config = BuildConfig(root_element="PayDoc", mode="maximal", repeat_count=2)
    result = build_xml(schema, config)
    assert validate_xml(result.xml_text, schema).valid
