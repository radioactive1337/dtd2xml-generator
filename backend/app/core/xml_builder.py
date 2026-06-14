"""XML document builder from parsed DTD schemas."""

from __future__ import annotations

import re
from typing import Literal

from lxml import etree
from pydantic import BaseModel, Field

from app.core.dtd_models import AttributeDef, ContentNode, DTDSchema, ElementDef

BuildMode = Literal["minimal", "maximal", "custom"]


class BuildConfig(BaseModel):
    schema_id: str = ""
    root_element: str
    mode: BuildMode = "minimal"
    repeat_count: int = Field(default=1, ge=1, le=100)
    custom_paths: set[str] = Field(default_factory=set)


class BuildResult(BaseModel):
    xml_text: str
    node_count: int
    warnings: list[str] = Field(default_factory=list)


class XMLBuilder:
    """Build XML trees from a DTDSchema in minimal, maximal, or custom mode."""

    def __init__(self, schema: DTDSchema, config: BuildConfig) -> None:
        self.schema = schema
        self.config = config
        self.warnings: list[str] = []
        self.node_count = 0

    def build(self) -> BuildResult:
        if self.config.root_element not in self.schema.elements:
            raise ValueError(f"Root element '{self.config.root_element}' not found in schema")

        root_def = self.schema.elements[self.config.root_element]
        root_el = self._build_element(root_def, self.config.root_element, parent_path="")
        xml_text = etree.tostring(
            root_el,
            pretty_print=True,
            encoding="UTF-8",
            xml_declaration=False,
        ).decode("UTF-8")
        return BuildResult(
            xml_text=xml_text,
            node_count=self.node_count,
            warnings=self.warnings,
        )

    def _build_element(
        self,
        elem_def: ElementDef,
        elem_name: str,
        parent_path: str,
    ) -> etree._Element:
        self.node_count += 1
        current_path = f"{parent_path}.{elem_name}" if parent_path else elem_name

        el = etree.Element(elem_name)
        self._apply_attributes(el, elem_def, current_path)
        self._build_content(el, elem_def.content_model, current_path, {elem_name})
        return el

    def _apply_attributes(
        self,
        el: etree._Element,
        elem_def: ElementDef,
        current_path: str,
    ) -> None:
        for name, attr in elem_def.attributes.items():
            if not self._should_include_attribute(attr, current_path, name):
                continue
            value = self._attribute_placeholder(attr)
            el.set(name, value)

    def _should_include_attribute(
        self,
        attr: AttributeDef,
        current_path: str,
        attr_name: str,
    ) -> bool:
        if attr.default_decl == "#REQUIRED":
            return True
        if self.config.mode == "minimal":
            return attr.default_decl.startswith("#FIXED")
        if self.config.mode == "maximal":
            return True
        # custom: required + optional if element path or attr path selected
        attr_path = f"{current_path}@{attr_name}"
        if attr.default_decl.startswith("#FIXED"):
            return True
        return current_path in self.config.custom_paths or attr_path in self.config.custom_paths

    def _attribute_placeholder(self, attr: AttributeDef) -> str:
        if constrained := attr.dtd_default_value():
            return constrained
        if attr.attr_type == "ENUM" and attr.allowed_values:
            return attr.allowed_values[0]
        if attr.attr_type == "ID":
            return "id-1"
        return ""

    def _build_content(
        self,
        parent_el: etree._Element,
        node: ContentNode,
        parent_path: str,
        ancestry: set[str],
    ) -> None:
        if node.kind == "EMPTY":
            return
        if node.kind == "ANY":
            if self.config.mode == "maximal":
                self.warnings.append(f"ANY content at '{parent_path}' — no child elements generated")
            return
        if node.kind == "PCDATA":
            parent_el.text = ""
            return
        if node.kind == "REF":
            self._expand_node(parent_el, node, parent_path, ancestry)
            return
        if node.kind == "SEQUENCE":
            for idx, child in enumerate(node.children):
                struct_path = self._child_path(parent_path, child, idx)
                expand_path = parent_path if child.kind == "REF" else struct_path
                self._expand_node(parent_el, child, expand_path, ancestry)
            return
        if node.kind == "CHOICE":
            options = self._select_choice_children(node, parent_path)
            for idx, child in enumerate(node.children):
                if child not in options:
                    continue
                child_path = self._child_path(parent_path, child, idx)
                self._expand_node(parent_el, child, child_path, ancestry)

    def _expand_node(
        self,
        parent_el: etree._Element,
        node: ContentNode,
        parent_path: str,
        ancestry: set[str],
    ) -> None:
        count = self._repeat_count(node)
        if count == 0:
            return
        for _ in range(count):
            if node.kind == "REF":
                self._append_ref(parent_el, node, parent_path, ancestry)
            else:
                self._build_content(parent_el, node, parent_path, ancestry)

    def _repeat_count(self, node: ContentNode) -> int:
        q = node.quantifier
        if self.config.mode == "minimal":
            if q in ("?", "*"):
                return 0
            return 1
        # maximal / custom
        if q in ("*", "+"):
            return self.config.repeat_count
        if q == "?":
            return 1
        return 1

    def _append_ref(
        self,
        parent_el: etree._Element,
        node: ContentNode,
        parent_path: str,
        ancestry: set[str],
    ) -> None:
        ref_name = node.ref
        if not ref_name:
            return

        child_path = f"{parent_path}.{ref_name}" if parent_path else ref_name
        if not self._should_include_element(ref_name, child_path, node):
            return

        if ref_name in ancestry:
            self.warnings.append(f"Cyclic reference skipped: {' -> '.join(ancestry)} -> {ref_name}")
            return

        child_def = self.schema.elements.get(ref_name)
        if child_def is None:
            self.warnings.append(f"Unknown element reference: {ref_name}")
            child_el = etree.SubElement(parent_el, ref_name)
            self.node_count += 1
            return

        new_ancestry = set(ancestry)
        new_ancestry.add(ref_name)
        child_el = etree.SubElement(parent_el, ref_name)
        self.node_count += 1
        self._apply_attributes(child_el, child_def, child_path)

        if child_def.content_model.kind == "PCDATA":
            child_el.text = ""
        else:
            self._build_content(child_el, child_def.content_model, child_path, new_ancestry)

    def _child_path(self, parent_path: str, child: ContentNode, index: int) -> str:
        child_name = child.ref if child.kind == "REF" else f"group-{index}"
        return f"{parent_path}.{child_name}" if parent_path else child_name

    def _normalize_custom_path(self, path: str) -> str:
        """Strip UI-only group-N segments so tree paths match element paths."""
        return re.sub(r"\.group-\d+(?=\.|$)", "", path)

    def _is_path_selected(self, path: str) -> bool:
        return self._choice_branch_score(path) > 0

    def _choice_branch_score(self, branch_path: str) -> int:
        """Count custom_paths that fall under branch_path (UI group-N aware)."""
        if branch_path in self.config.custom_paths:
            return 10
        prefix = branch_path + "."
        score = 0
        for p in self.config.custom_paths:
            if p.startswith(prefix):
                score += 1
        if score:
            return score
        normalized_branch = self._normalize_custom_path(branch_path)
        if normalized_branch in {self._normalize_custom_path(p) for p in self.config.custom_paths}:
            return 1
        norm_prefix = normalized_branch + "."
        for p in self.config.custom_paths:
            if self._normalize_custom_path(p).startswith(norm_prefix):
                score += 1
        return score

    def _should_include_element(
        self,
        ref_name: str,
        child_path: str,
        node: ContentNode,
    ) -> bool:
        if self.config.mode == "minimal":
            return node.quantifier not in ("?", "*")

        if self.config.mode == "maximal":
            return True

        # custom: required children (no ?/*) always; others if path matches
        if node.quantifier not in ("?", "*"):
            return True
        return self._is_path_selected(child_path)

    def _select_choice_children(self, node: ContentNode, parent_path: str) -> list[ContentNode]:
        if self.config.mode == "maximal":
            if not node.children:
                return []
            return [self._pick_richest_choice_child(node.children)]

        if self.config.mode == "minimal":
            for child in node.children:
                if child.kind == "REF" and child.quantifier not in ("?", "*"):
                    return [child]
                if child.kind != "REF" and child.quantifier not in ("?", "*"):
                    return [child]
            return []

        # custom: pick the best-matching branch (CHOICE is exclusive)
        best_child: ContentNode | None = None
        best_score = 0
        best_path_len = -1
        for idx, child in enumerate(node.children):
            child_path = self._child_path(parent_path, child, idx)
            score = self._choice_branch_score(child_path)
            path_len = len(child_path)
            if score > best_score or (
                score == best_score and score > 0 and path_len > best_path_len
            ):
                best_score = score
                best_path_len = path_len
                best_child = child
        if best_child is not None and best_score > 0:
            return [best_child]

        if node.quantifier in ("?", "*"):
            return []

        for child in node.children:
            if child.quantifier not in ("?", "*"):
                return [child]
        return [node.children[0]] if node.children else []


    def _pick_richest_choice_child(self, options: list[ContentNode]) -> ContentNode:
        """Pick the choice branch that yields the largest subtree in maximal mode."""
        return max(options, key=self._choice_branch_weight)

    def _choice_branch_weight(self, node: ContentNode) -> int:
        if node.kind == "REF":
            child_def = self.schema.elements.get(node.ref)
            inner = self._content_weight(child_def.content_model) if child_def else 1
            if node.quantifier in ("*", "+"):
                return inner * self.config.repeat_count
            if node.quantifier == "?":
                return inner
            return inner
        if node.kind == "SEQUENCE":
            return sum(self._choice_branch_weight(child) for child in node.children)
        if node.kind == "CHOICE":
            if not node.children:
                return 0
            return max(self._choice_branch_weight(child) for child in node.children)
        if node.kind == "PCDATA":
            return 1
        return 0

    def _content_weight(self, node: ContentNode) -> int:
        if node.kind in ("EMPTY", "ANY"):
            return 0
        if node.kind == "PCDATA":
            return 1
        if node.kind == "REF":
            return self._choice_branch_weight(node)
        if node.kind == "SEQUENCE":
            total = sum(self._content_weight(child) for child in node.children)
            if node.quantifier in ("*", "+"):
                return total * self.config.repeat_count
            if node.quantifier == "?":
                return total
            return total
        if node.kind == "CHOICE":
            if not node.children:
                return 0
            pick = max(self._choice_branch_weight(child) for child in node.children)
            if node.quantifier in ("*", "+"):
                return pick * self.config.repeat_count
            if node.quantifier == "?":
                return pick
            return pick
        return 0


def build_xml(schema: DTDSchema, config: BuildConfig) -> BuildResult:
    """Build XML from a parsed DTD schema."""
    return XMLBuilder(schema, config).build()
