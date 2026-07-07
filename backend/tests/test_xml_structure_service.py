"""Tests for the XML structure comparison service."""

import pytest

from app.services import xml_structure_service as svc
from app.services.xml_structure_service import ReferenceDoc, XmlParseError


def test_extract_paths_ignores_attribute_order_and_whitespace():
    a = '<PayDoc><client name="A" id="1"><contact/></client></PayDoc>'
    b = (
        "<PayDoc>\n"
        '  <client id="1" name="A">\n'
        "    <contact></contact>\n"
        "  </client>\n"
        "</PayDoc>\n"
    )
    assert svc.extract_paths(a) == svc.extract_paths(b)
    assert svc.extract_paths(a) == {
        "PayDoc",
        "PayDoc/client",
        "PayDoc/client/contact",
    }


def test_extract_paths_ignores_namespace():
    xml = '<ns:PayDoc xmlns:ns="urn:x"><ns:client/></ns:PayDoc>'
    assert svc.extract_paths(xml) == {"PayDoc", "PayDoc/client"}


def test_extract_paths_deduplicates_repeated_siblings():
    xml = "<PayDoc><item/><item/><item/></PayDoc>"
    assert svc.extract_paths(xml) == {"PayDoc", "PayDoc/item"}


def test_peek_root_element_strips_namespace():
    assert svc.peek_root_element('<ns:PayDoc xmlns:ns="urn:x"/>') == "PayDoc"


def test_parse_error_raised_for_invalid_xml():
    with pytest.raises(XmlParseError):
        svc.extract_paths("<PayDoc><unclosed></PayDoc>")
    with pytest.raises(XmlParseError):
        svc.peek_root_element("   ")


def test_compare_structure_finds_unique_paths():
    current = "<PayDoc><client><contact/></client><newBlock><inner/></newBlock></PayDoc>"
    refs = [
        ReferenceDoc("cat", "ref1", "Ref 1", "<PayDoc><client><contact/></client></PayDoc>"),
    ]
    report = svc.compare_structure(current, refs)
    assert report["root_element"] == "PayDoc"
    assert report["is_unique"] is True
    assert report["unique_paths"] == ["PayDoc/newBlock", "PayDoc/newBlock/inner"]
    assert report["references_count"] == 1
    assert report["has_references"] is True


def test_compare_structure_not_unique_when_subset_of_union():
    current = "<PayDoc><a/><b/></PayDoc>"
    refs = [
        ReferenceDoc("c", "r1", "R1", "<PayDoc><a/></PayDoc>"),
        ReferenceDoc("c", "r2", "R2", "<PayDoc><b/></PayDoc>"),
    ]
    report = svc.compare_structure(current, refs)
    assert report["is_unique"] is False
    assert report["unique_paths"] == []


def test_compare_structure_jaccard_and_closest():
    current = "<PayDoc><a/><b/></PayDoc>"  # paths: PayDoc, PayDoc/a, PayDoc/b
    refs = [
        ReferenceDoc("c", "close", "Close", "<PayDoc><a/><b/></PayDoc>"),
        ReferenceDoc("c", "far", "Far", "<PayDoc><z/></PayDoc>"),
    ]
    report = svc.compare_structure(current, refs)
    scores = {s["doc_id"]: s["score"] for s in report["similarities"]}
    assert scores["close"] == 1.0
    # union {PayDoc,a,b,z} = 4, intersection {PayDoc} = 1
    assert scores["far"] == pytest.approx(0.25)
    assert report["closest"]["doc_id"] == "close"
    # sorted descending by score
    assert report["similarities"][0]["doc_id"] == "close"


def test_compare_structure_without_references():
    report = svc.compare_structure("<PayDoc><a/></PayDoc>", [])
    assert report["has_references"] is False
    assert report["references_count"] == 0
    # everything is unique when there are no references
    assert report["is_unique"] is True
    assert report["unique_paths"] == ["PayDoc", "PayDoc/a"]


def test_compare_structure_skips_unparseable_reference():
    refs = [
        ReferenceDoc("c", "bad", "Bad", "<broken>"),
        ReferenceDoc("c", "ok", "Ok", "<PayDoc><a/></PayDoc>"),
    ]
    report = svc.compare_structure("<PayDoc><a/></PayDoc>", refs)
    assert report["references_count"] == 1
    assert report["similarities"][0]["doc_id"] == "ok"


def test_highlight_ranges_cover_topmost_unique_subtree():
    current = (
        "<PayDoc>\n"
        "  <client/>\n"
        "  <newBlock>\n"
        "    <inner/>\n"
        "  </newBlock>\n"
        "</PayDoc>\n"
    )
    refs = [ReferenceDoc("c", "r", "R", "<PayDoc><client/></PayDoc>")]
    report = svc.compare_structure(current, refs)
    ranges = report["highlight_ranges"]
    # Only the top-most divergence (newBlock) is emitted, not its unique child.
    assert len(ranges) == 1
    assert ranges[0]["path"] == "PayDoc/newBlock"
    assert ranges[0]["start_line"] == 3
    # sourceline tracks start tags, so the range ends at <inner/> (line 4).
    assert ranges[0]["end_line"] == 4


def test_extract_snippets_truncates_and_targets_topmost():
    current = "<PayDoc><client/><newBlock><inner/></newBlock></PayDoc>"
    snippets = svc.extract_snippets(current, ["PayDoc/newBlock", "PayDoc/newBlock/inner"])
    assert len(snippets) == 1
    assert snippets[0]["path"] == "PayDoc/newBlock"
    assert "newBlock" in snippets[0]["xml"]

    long_snips = svc.extract_snippets(current, ["PayDoc/newBlock"], max_length=10)
    assert long_snips[0]["xml"].endswith("…")
