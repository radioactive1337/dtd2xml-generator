"""Pydantic models representing a parsed DTD schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ContentNodeKind = Literal["EMPTY", "ANY", "PCDATA", "SEQUENCE", "CHOICE", "REF"]


class ContentNode(BaseModel):
    """Recursive content model tree node."""

    kind: ContentNodeKind
    children: list[ContentNode] = Field(default_factory=list)
    ref: str = ""
    quantifier: str = ""  # "" | "?" | "*" | "+"


class AttributeDef(BaseModel):
    """DTD attribute definition."""

    name: str
    attr_type: str  # CDATA | ID | NMTOKEN | ENUM | ...
    default_decl: str  # #REQUIRED | #IMPLIED | #FIXED | literal
    allowed_values: list[str] = Field(default_factory=list)
    doc: str = ""

    def locked_value(self) -> str | None:
        """Value that must not vary: ``#FIXED`` or a single-value enum."""
        if self.default_decl.startswith("#FIXED"):
            return self.default_decl.replace("#FIXED", "").strip().strip("\"'")
        if self.attr_type == "ENUM" and len(self.allowed_values) == 1:
            return self.allowed_values[0]
        return None

    def dtd_default_value(self) -> str | None:
        """Return a DTD-provided default, if any.

        This includes ``#FIXED``, single-value enums, and quoted literal
        defaults such as ``"email"``. A literal default on a multi-value
        enum is a fallback, not a lock — use :meth:`locked_value` when the
        value must not change.
        """
        if locked := self.locked_value():
            return locked
        if self.default_decl and not self.default_decl.startswith("#"):
            return self.default_decl.strip().strip("\"'")
        return None

    def is_declared_default(self) -> bool:
        """True when the DTD names a concrete value that fill should not invent.

        Covers ``#FIXED``, a single-value enum, and quoted CDATA literals
        such as ``document_type CDATA "d"``. A literal on a multi-value enum
        is only a fill fallback, not a declared default in this sense.
        """
        if self.locked_value():
            return True
        if self.attr_type == "ENUM":
            return False
        return self.dtd_default_value() is not None


class ElementDef(BaseModel):
    """DTD element definition with parsed content model and attributes."""

    name: str
    content_raw: str
    content_model: ContentNode
    attributes: dict[str, AttributeDef] = Field(default_factory=dict)
    doc: str = ""


class DTDSchema(BaseModel):
    """Complete parsed DTD schema."""

    elements: dict[str, ElementDef] = Field(default_factory=dict)
    param_entities: dict[str, str] = Field(default_factory=dict)
    source_files: list[str] = Field(default_factory=list)

    def root_elements(self) -> list[str]:
        """Return element names sorted alphabetically."""
        return sorted(self.elements.keys())
