"""Tests for dot-path element resolution."""

from lxml import etree

from app.core.xml_tree import find_elements_by_dot_path, normalize_dot_path


SAMPLE_XML = """\
<PayDoc>
  <Body>
    <client inn="1" name="A"/>
    <client inn="2" name="B"/>
  </Body>
  <Body>
    <client inn="3" name="C"/>
  </Body>
</PayDoc>
"""


def _parse(xml: str = SAMPLE_XML) -> etree._Element:
    return etree.fromstring(xml.encode("utf-8"))


def test_normalize_dot_path_strips_group_segments():
    assert normalize_dot_path("PayDoc.group-0.Body.client") == "PayDoc.Body.client"


def test_find_elements_by_dot_path_exact():
    root = _parse()
    matches = find_elements_by_dot_path(root, "PayDoc.Body.client")
    assert len(matches) == 1
    assert matches[0].get("inn") == "1"


def test_find_elements_by_dot_path_second_body():
    root = _parse()
    matches = find_elements_by_dot_path(root, "PayDoc.Body.client")
    # First Body's first client
    assert matches[0].get("name") == "A"

    # Walk to second Body manually to verify path resolution picks first match
    bodies = list(root.findall("Body"))
    second_client = bodies[1].find("client")
    assert second_client is not None
    assert second_client.get("inn") == "3"


def test_find_elements_by_dot_path_not_found():
    root = _parse()
    assert find_elements_by_dot_path(root, "PayDoc.Missing.client") == []


def test_find_elements_by_dot_path_root_mismatch():
    root = _parse()
    assert find_elements_by_dot_path(root, "Other.Body.client") == []
