"""Validate XML documents against a parsed DTD schema."""

from __future__ import annotations

import threading
from io import BytesIO

from lxml import etree
from pydantic import BaseModel, Field

from app.core.dtd_exporter import export_flat_dtd
from app.core.dtd_models import DTDSchema
from app.core.xml_dtd_normalize import normalize_xml_for_dtd_validation

_compiled_dtd_cache: dict[int, etree.DTD] = {}
_dtd_cache_lock = threading.Lock()


class ValidationError(BaseModel):
    line: int
    column: int
    message: str
    level: str = "error"


class ValidationResult(BaseModel):
    valid: bool
    errors: list[ValidationError] = Field(default_factory=list)


def _schema_fingerprint(schema: DTDSchema) -> int:
    return hash(schema.model_dump_json())


def _get_compiled_dtd(schema: DTDSchema) -> etree.DTD:
    """Return a compiled libxml2 DTD, reusing cached instances per schema content."""
    key = _schema_fingerprint(schema)
    with _dtd_cache_lock:
        cached = _compiled_dtd_cache.get(key)
        if cached is not None:
            return cached

    flat_dtd = export_flat_dtd(schema)
    dtd = etree.DTD(BytesIO(flat_dtd.encode("utf-8")))

    with _dtd_cache_lock:
        _compiled_dtd_cache[key] = dtd
    return dtd


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
        dtd = _get_compiled_dtd(schema)
    except ValueError as exc:
        return ValidationResult(
            valid=False,
            errors=[ValidationError(line=0, column=0, message=str(exc))],
        )
    except etree.DTDParseError as exc:
        return ValidationResult(
            valid=False,
            errors=[ValidationError(line=0, column=0, message=f"DTD error: {exc}")],
        )

    # Normalization strips sourceline info from elements (lxml sets it read-only during
    # parsing only). Skip it when no namespace prefixes are present — which covers
    # virtually all DTD-validated XML — so error_log entries get correct line numbers.
    validation_root = normalize_xml_for_dtd_validation(root) if root.nsmap else root

    try:
        dtd.assertValid(validation_root)
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
