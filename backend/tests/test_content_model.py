"""Tests for DTD content model parser."""

import pytest

from app.core.content_model import ContentModelParseError, parse_content_model


def test_empty_and_any():
    assert parse_content_model("EMPTY").kind == "EMPTY"
    assert parse_content_model("ANY").kind == "ANY"


def test_simple_sequence():
    node = parse_content_model("(Header, Body, Footer?)")
    assert node.kind == "SEQUENCE"
    assert len(node.children) == 3
    assert node.children[0].ref == "Header"
    assert node.children[2].ref == "Footer"
    assert node.children[2].quantifier == "?"


def test_choice_with_quantifier():
    node = parse_content_model("(Field | Group)*")
    assert node.kind == "CHOICE"
    assert node.quantifier == "*"
    refs = [c.ref for c in node.children]
    assert refs == ["Field", "Group"]


def test_one_or_more():
    node = parse_content_model("Record+")
    assert node.kind == "REF"
    assert node.ref == "Record"
    assert node.quantifier == "+"


def test_mixed_content():
    node = parse_content_model("(#PCDATA)")
    assert node.kind == "PCDATA"

    node = parse_content_model("(#PCDATA | child)*")
    assert node.kind == "CHOICE"
    assert node.quantifier == "*"
    kinds = [c.kind for c in node.children]
    assert "PCDATA" in kinds


def test_nested_group():
    node = parse_content_model("(A, (B | C+)?, D*)")
    assert node.kind == "SEQUENCE"
    assert len(node.children) == 3
    choice = node.children[1]
    assert choice.kind == "CHOICE"
    assert choice.quantifier == "?"


def test_invalid_model_raises():
    with pytest.raises(ContentModelParseError):
        parse_content_model("")
