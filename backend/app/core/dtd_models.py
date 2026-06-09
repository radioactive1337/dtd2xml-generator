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
