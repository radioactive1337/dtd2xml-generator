"""Validate XML documents against a parsed DTD schema."""

from __future__ import annotations

from io import BytesIO

from lxml import etree
from pydantic import BaseModel, Field

from app.core.dtd_exporter import export_flat_dtd
from app.core.dtd_models import DTDSchema


class ValidationError(BaseModel):
    line: int
    column: int
    message: str
    level: str = "error"


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationError] = Field(default_factory=list)


def validate_xml(xml_text: str, schema: DTDSchema) -> ValidationResult:
    """Validate XML text against the given DTD schema."""
    if not xml_text.strip():
        return ValidationResult(
            valid=False,
            errors=[ValidationError(line=0, column=0, message="XML is empty")],
        )

    try:
        root = etree.fromstring(xml_text.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        return ValidationResult(
            valid=False,
            errors=[
                ValidationError(
                    line=exc.lineno or 0,
                    column=exc.offset or 0,
                    message=str(exc),
                )
            ],
        )

    try:
        flat_dtd = export_flat_dtd(schema)
    except ValueError as exc:
        return ValidationResult(
            valid=False,
            errors=[ValidationError(line=0, column=0, message=str(exc))],
        )

    try:
        dtd = etree.DTD(BytesIO(flat_dtd.encode("utf-8")))
    except etree.DTDParseError as exc:
        return ValidationResult(
            valid=False,
            errors=[ValidationError(line=0, column=0, message=f"DTD error: {exc}")],
        )

    try:
        dtd.assertValid(root)
    except etree.DocumentInvalid:
        errors = [
            ValidationError(
                line=entry.line,
                column=entry.column,
                message=entry.message,
                level=entry.level_name.lower(),
            )
            for entry in dtd.error_log
        ]
        if not errors:
            errors = [
                ValidationError(
                    line=0,
                    column=0,
                    message="Document does not conform to DTD",
                )
            ]
        return ValidationResult(valid=False, errors=errors)

    return ValidationResult(valid=True)
