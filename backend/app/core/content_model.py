"""Recursive descent parser for DTD content model expressions."""

from __future__ import annotations

from app.core.dtd_models import ContentNode


class ContentModelParseError(ValueError):
    """Raised when a content model string cannot be parsed."""


class ContentModelParser:
    """Parses DTD content model strings into ContentNode trees."""

    def __init__(self, text: str) -> None:
        self._text = text.strip()
        self._pos = 0
        self._length = len(self._text)

    def parse(self) -> ContentNode:
        if not self._text:
            raise ContentModelParseError("Empty content model")

        upper = self._text.upper()
        if upper == "EMPTY":
            return ContentNode(kind="EMPTY")
        if upper == "ANY":
            return ContentNode(kind="ANY")

        node = self._parse_expr()
        self._skip_ws()
        if self._pos < self._length:
            raise ContentModelParseError(
                f"Unexpected trailing input at position {self._pos}: "
                f"{self._text[self._pos :]!r}"
            )
        return node

    def _parse_expr(self) -> ContentNode:
        self._skip_ws()
        if self._peek() == "(":
            return self._parse_group()
        return self._parse_atom()

    def _parse_group(self) -> ContentNode:
        self._consume("(")
        self._skip_ws()

        if self._match("#PCDATA"):
            self._skip_ws()
            if self._peek() == ")":
                self._consume(")")
                quantifier = self._parse_quantifier()
                return ContentNode(kind="PCDATA", quantifier=quantifier)

            # Mixed content: (#PCDATA | child1 | child2)*
            self._consume("|")
            children: list[ContentNode] = [ContentNode(kind="PCDATA")]
            while True:
                self._skip_ws()
                children.append(self._parse_atom())
                self._skip_ws()
                if self._peek() == "|":
                    self._consume("|")
                    continue
                break

            self._consume(")")
            quantifier = self._parse_quantifier()
            return ContentNode(kind="CHOICE", children=children, quantifier=quantifier)

        first = self._parse_expr()
        self._skip_ws()

        if self._peek() == ",":
            children = [first]
            while self._peek() == ",":
                self._consume(",")
                self._skip_ws()
                children.append(self._parse_expr())
                self._skip_ws()
            self._consume(")")
            quantifier = self._parse_quantifier()
            return ContentNode(kind="SEQUENCE", children=children, quantifier=quantifier)

        if self._peek() == "|":
            children = [first]
            while self._peek() == "|":
                self._consume("|")
                self._skip_ws()
                children.append(self._parse_expr())
                self._skip_ws()
            self._consume(")")
            quantifier = self._parse_quantifier()
            return ContentNode(kind="CHOICE", children=children, quantifier=quantifier)

        # Single parenthesized expression: (A)?
        self._consume(")")
        quantifier = self._parse_quantifier()
        if quantifier:
            first.quantifier = quantifier
        return first

    def _parse_atom(self) -> ContentNode:
        self._skip_ws()
        if self._match("#PCDATA"):
            quantifier = self._parse_quantifier()
            return ContentNode(kind="PCDATA", quantifier=quantifier)

        start = self._pos
        while self._pos < self._length:
            ch = self._text[self._pos]
            if ch.isalnum() or ch in "._-:":
                self._pos += 1
                continue
            break

        name = self._text[start : self._pos].strip()
        if not name:
            raise ContentModelParseError(
                f"Expected element name at position {self._pos}"
            )

        quantifier = self._parse_quantifier()
        return ContentNode(kind="REF", ref=name, quantifier=quantifier)

    def _parse_quantifier(self) -> str:
        self._skip_ws()
        if self._pos >= self._length:
            return ""
        ch = self._text[self._pos]
        if ch in "?*+":
            self._pos += 1
            return ch
        return ""

    def _skip_ws(self) -> None:
        while self._pos < self._length and self._text[self._pos].isspace():
            self._pos += 1

    def _peek(self) -> str:
        self._skip_ws()
        if self._pos >= self._length:
            return ""
        return self._text[self._pos]

    def _consume(self, expected: str) -> None:
        self._skip_ws()
        if not self._text.startswith(expected, self._pos):
            raise ContentModelParseError(
                f"Expected {expected!r} at position {self._pos}, "
                f"got {self._text[self._pos : self._pos + len(expected)]!r}"
            )
        self._pos += len(expected)

    def _match(self, token: str) -> bool:
        self._skip_ws()
        if self._text[self._pos : self._pos + len(token)].upper() == token.upper():
            self._pos += len(token)
            return True
        return False


def parse_content_model(text: str) -> ContentNode:
    """Parse a DTD content model string into a ContentNode tree."""
    return ContentModelParser(text).parse()
