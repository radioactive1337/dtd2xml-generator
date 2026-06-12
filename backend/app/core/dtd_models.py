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

    def dtd_default_value(self) -> str | None:
        """Return a single constrained value from the DTD, if any."""
        if self.default_decl.startswith("#FIXED"):
            return self.default_decl.replace("#FIXED", "").strip().strip("\"'")
        if self.default_decl and not self.default_decl.startswith("#"):
            return self.default_decl.strip().strip("\"'")
        if self.attr_type == "ENUM" and len(self.allowed_values) == 1:
            return self.allowed_values[0]
        return None


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
