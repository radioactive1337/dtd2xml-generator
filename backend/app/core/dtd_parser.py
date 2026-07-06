"""Three-pass DTD parser with external entity resolution and comment extraction."""

from __future__ import annotations

import re
from pathlib import Path

from app.core.content_model import ContentModelParseError, parse_content_model
from app.core.dtd_models import AttributeDef, DTDSchema, ElementDef

# DTD names: elements/attrs use hyphens, underscores, and optional namespace prefixes
_ELEMENT_NAME = r"(?:[a-zA-Z][-a-zA-Z0-9_]*:)?[a-zA-Z][-a-zA-Z0-9_]*"
_PARAM_ENTITY_NAME = r"[a-zA-Z][-a-zA-Z0-9_.]*"

# Parameter entity declarations
_ENTITY_PARAM_RE = re.compile(
    rf"<!ENTITY\s+%\s+({_PARAM_ENTITY_NAME})\s+"
    r'(?:"([^"]*)"|\'([^\']*)\'|SYSTEM\s+"([^"]+)"|SYSTEM\s+\'([^\']+)\')\s*>',
    re.IGNORECASE | re.DOTALL,
)

# XML comments
_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)

# Element and attribute declarations
_ELEMENT_DECL_RE = re.compile(
    rf"<!ELEMENT\s+({_ELEMENT_NAME})\s+([^>]+)>", re.IGNORECASE | re.DOTALL
)
_ATTLIST_DECL_RE = re.compile(
    rf"<!ATTLIST\s+({_ELEMENT_NAME})\s+([^>]+)>", re.IGNORECASE | re.DOTALL
)

# @doc and @att tags inside comments
_DOC_TAG_RE = re.compile(r"@doc\s+(.+)", re.IGNORECASE)
_ATT_TAG_RE = re.compile(
    rf"@att\s+({_ELEMENT_NAME})\s+(.+)", re.IGNORECASE
)

# Parameter entity references (names may contain dots: %amount.content;)
_PARAM_REF_RE = re.compile(rf"%({_PARAM_ENTITY_NAME});")

# Attribute line within ATTLIST: name type default
_ATTR_LINE_RE = re.compile(
    rf"({_ELEMENT_NAME})\s+"
    rf"(\([^)]+\)|%{_PARAM_ENTITY_NAME};|CDATA|ID|IDREF|IDREFS|ENTITY|ENTITIES|NMTOKEN|NMTOKENS|NOTATION\s+\([^)]+\))\s+"
    r"(#\w+(?:\s+\"[^\"]*\")?|\"[^\"]*\"|'[^']*')",
    re.IGNORECASE,
)


class DTDParser:
    """Parse DTD files into a structured DTDSchema."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self._param_entities: dict[str, str] = {}
        self._source_files: list[str] = []
        self._loaded_files: set[Path] = set()

    def parse_file(self, path: Path | str) -> DTDSchema:
        """Parse a DTD file from disk."""
        file_path = Path(path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"DTD file not found: {file_path}")

        self.base_dir = file_path.parent
        self._param_entities.clear()
        self._source_files.clear()
        self._loaded_files.clear()

        raw_text = self._load_dtd_text(file_path)
        return self._build_schema(raw_text)

    def parse_string(self, text: str, base_dir: Path | str | None = None) -> DTDSchema:
        """Parse DTD text directly (useful for tests)."""
        if base_dir is not None:
            self.base_dir = Path(base_dir)
        self._param_entities.clear()
        self._source_files.clear()
        self._loaded_files.clear()
        return self._build_schema(text)

    def _load_dtd_text(self, path: Path) -> str:
        """Recursively load DTD text including external SYSTEM entity files."""
        resolved = path.resolve()
        if resolved in self._loaded_files:
            return ""
        self._loaded_files.add(resolved)
        self._source_files.append(str(resolved))

        text = resolved.read_text(encoding="utf-8", errors="replace")

        # Pre-load external SYSTEM entity files referenced in this file
        for match in _ENTITY_PARAM_RE.finditer(text):
            system_path = match.group(4) or match.group(5)
            if system_path:
                external = (self.base_dir / system_path).resolve()
                if external.exists() and external not in self._loaded_files:
                    self._load_dtd_text(external)

        return text

    def _build_schema(self, raw_text: str) -> DTDSchema:
        """Run all three passes and return the parsed schema."""
        self._collect_entities(raw_text)
        expanded = self._substitute_entities(raw_text)
        return self._parse_declarations(expanded)

    # --- Pass 1: Entity collection ---

    def _collect_entities(self, text: str) -> None:
        """Collect all parameter entity definitions from text and loaded files."""
        for source in self._source_files:
            source_text = Path(source).read_text(encoding="utf-8", errors="replace")
            for match in _ENTITY_PARAM_RE.finditer(source_text):
                name = match.group(1)
                value = match.group(2) or match.group(3) or ""
                if match.group(4) or match.group(5):
                    system_path = match.group(4) or match.group(5)
                    external = (self.base_dir / system_path).resolve()
                    if external.exists():
                        value = external.read_text(encoding="utf-8", errors="replace")
                self._param_entities[name] = value.strip()

        # Also scan the main text for inline entities
        for match in _ENTITY_PARAM_RE.finditer(text):
            name = match.group(1)
            if name not in self._param_entities:
                value = match.group(2) or match.group(3) or ""
                self._param_entities[name] = value.strip()

    # --- Pass 2: Entity substitution ---

    def _substitute_entities(self, text: str) -> str:
        """Replace all %entity; references with their values."""
        # Remove entity declarations themselves (they are metadata, not content)
        text = _ENTITY_PARAM_RE.sub("", text)

        max_iterations = 50
        for _ in range(max_iterations):
            changed = False

            def replacer(m: re.Match[str]) -> str:
                nonlocal changed
                name = m.group(1)
                if name in self._param_entities:
                    changed = True
                    return self._param_entities[name]
                return m.group(0)

            new_text = _PARAM_REF_RE.sub(replacer, text)
            if not changed:
                break
            text = new_text

        return text

    # --- Pass 3: Declaration parsing ---

    def _parse_declarations(self, text: str) -> DTDSchema:
        """Parse ELEMENT and ATTLIST declarations with preceding comments."""
        elements: dict[str, ElementDef] = {}
        pending_comments: list[str] = []
        att_docs: dict[str, dict[str, str]] = {}  # element -> attr -> doc

        # Tokenize into comments and declarations in order
        tokens = self._tokenize(text)

        for token_type, token_value in tokens:
            if token_type == "comment":
                pending_comments.append(token_value)
            elif token_type == "element":
                elem_name, content_raw = token_value
                doc, attr_docs = self._extract_comment_metadata(pending_comments)
                pending_comments.clear()

                content_raw = content_raw.strip()
                try:
                    content_model = parse_content_model(content_raw)
                except ContentModelParseError:
                    content_model = parse_content_model("ANY")

                elements[elem_name] = ElementDef(
                    name=elem_name,
                    content_raw=content_raw,
                    content_model=content_model,
                    doc=doc,
                )
                if attr_docs:
                    att_docs[elem_name] = attr_docs

            elif token_type == "attlist":
                elem_name, attlist_body = token_value
                doc, attr_docs = self._extract_comment_metadata(pending_comments)
                pending_comments.clear()

                if elem_name not in att_docs:
                    att_docs[elem_name] = {}
                att_docs[elem_name].update(attr_docs)

                if elem_name not in elements:
                    elements[elem_name] = ElementDef(
                        name=elem_name,
                        content_raw="ANY",
                        content_model=parse_content_model("ANY"),
                        doc=doc,
                    )

                self._parse_attlist_body(
                    elements[elem_name], attlist_body, att_docs.get(elem_name, {})
                )

        return DTDSchema(
            elements=elements,
            param_entities=dict(self._param_entities),
            source_files=list(self._source_files),
        )

    def _tokenize(self, text: str) -> list[tuple[str, str | tuple[str, str]]]:
        """Split DTD text into ordered comments and declarations."""
        tokens: list[tuple[str, str | tuple[str, str]]] = []
        pos = 0
        length = len(text)

        while pos < length:
            # Skip whitespace
            if text[pos].isspace():
                pos += 1
                continue

            # Comment
            if text.startswith("<!--", pos):
                end = text.find("-->", pos + 4)
                if end == -1:
                    break
                comment_body = text[pos + 4 : end]
                tokens.append(("comment", comment_body))
                pos = end + 3
                continue

            # ELEMENT declaration
            elem_match = _ELEMENT_DECL_RE.match(text, pos)
            if elem_match:
                tokens.append(
                    ("element", (elem_match.group(1), elem_match.group(2)))
                )
                pos = elem_match.end()
                continue

            # ATTLIST declaration
            att_match = _ATTLIST_DECL_RE.match(text, pos)
            if att_match:
                tokens.append(
                    ("attlist", (att_match.group(1), att_match.group(2)))
                )
                pos = att_match.end()
                continue

            pos += 1

        return tokens

    def _extract_comment_metadata(
        self, comments: list[str]
    ) -> tuple[str, dict[str, str]]:
        """Extract @doc and @att metadata from comment blocks."""
        doc_parts: list[str] = []
        attr_docs: dict[str, str] = {}

        for comment in comments:
            for line in comment.splitlines():
                line = line.strip()
                if not line:
                    continue

                doc_match = _DOC_TAG_RE.search(line)
                if doc_match:
                    doc_parts.append(doc_match.group(1).strip())
                    continue

                att_match = _ATT_TAG_RE.search(line)
                if att_match:
                    attr_name = att_match.group(1)
                    attr_doc = att_match.group(2).strip()
                    attr_docs[attr_name] = attr_doc
                    continue

                # Plain comment text (no @tag) — treat as doc context
                if not line.startswith("@"):
                    doc_parts.append(line)

        return " ".join(doc_parts), attr_docs

    def _expand_entity_refs(self, text: str) -> str:
        """Substitute remaining %entity; references in a fragment."""

        def replacer(m: re.Match[str]) -> str:
            name = m.group(1)
            return self._param_entities.get(name, m.group(0))

        return _PARAM_REF_RE.sub(replacer, text)

    def _parse_attlist_body(
        self,
        element: ElementDef,
        body: str,
        attr_docs: dict[str, str],
    ) -> None:
        """Parse attribute lines from an ATTLIST declaration body."""
        body = self._expand_entity_refs(body)
        normalized = re.sub(r"\s+", " ", body.strip())

        for match in _ATTR_LINE_RE.finditer(normalized):
            attr_name = match.group(1)
            attr_type_raw = match.group(2).strip()
            default_decl = match.group(3).strip()

            allowed_values: list[str] = []
            attr_type = attr_type_raw

            enum_match = re.match(r"\(([^)]+)\)", attr_type_raw)
            if enum_match:
                attr_type = "ENUM"
                allowed_values = [
                    v.strip().strip("\"'")
                    for v in enum_match.group(1).split("|")
                ]

            element.attributes[attr_name] = AttributeDef(
                name=attr_name,
                attr_type=attr_type,
                default_decl=default_decl,
                allowed_values=allowed_values,
                doc=attr_docs.get(attr_name, ""),
            )
