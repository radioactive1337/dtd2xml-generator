"""Smart Faker-based XML data population."""

from __future__ import annotations

import random
import re
from typing import Any

from faker import Faker
from lxml import etree

from app.core.dtd_models import AttributeDef, DTDSchema, ElementDef
from app.core.xml_tree import ProtectedAttrs, element_path

_DEFAULT_LOCALE = "ru_RU"


class FakerService:
    """Populate XML element/attribute values using name-based heuristics."""

    def __init__(self, locale: str = _DEFAULT_LOCALE) -> None:
        self.faker = Faker(locale)

    def populate_xml(
        self,
        xml_text: str,
        schema: DTDSchema,
        *,
        fill_empty_only: bool = False,
        protected_attrs: ProtectedAttrs = frozenset(),
    ) -> str:
        root = etree.fromstring(xml_text.encode("utf-8"))
        self._populate_element(
            root,
            schema,
            fill_empty_only=fill_empty_only,
            protected_attrs=protected_attrs,
        )
        return etree.tostring(
            root,
            pretty_print=True,
            encoding="UTF-8",
            xml_declaration=False,
        ).decode("UTF-8")

    def _populate_element(
        self,
        el: etree._Element,
        schema: DTDSchema,
        *,
        fill_empty_only: bool = False,
        protected_attrs: ProtectedAttrs = frozenset(),
    ) -> None:
        elem_def = schema.elements.get(el.tag)
        if elem_def is None:
            for child in el:
                self._populate_element(
                    child,
                    schema,
                    fill_empty_only=fill_empty_only,
                    protected_attrs=protected_attrs,
                )
            return

        path = element_path(el)
        for attr_name, attr_value in list(el.attrib.items()):
            if (path, attr_name) in protected_attrs:
                continue
            should_fill = (
                not fill_empty_only
                or not attr_value.strip()
                or bool(protected_attrs)
            )
            if not should_fill:
                continue
            attr_def = elem_def.attributes.get(attr_name)
            el.set(attr_name, self.generate_attribute_value(attr_name, attr_def))

        if elem_def.content_model.kind == "PCDATA" and (el.text is None or el.text == ""):
            el.text = self.generate_text_value(el.tag, elem_def)

        for child in el:
            self._populate_element(
                child,
                schema,
                fill_empty_only=fill_empty_only,
                protected_attrs=protected_attrs,
            )

    def generate_attribute_value(
        self,
        name: str,
        attr_def: AttributeDef | None = None,
    ) -> str:
        if attr_def and attr_def.default_decl.startswith("#FIXED"):
            return attr_def.default_decl.replace("#FIXED", "").strip().strip("\"'")
        if attr_def and attr_def.attr_type == "ENUM" and attr_def.allowed_values:
            return random.choice(attr_def.allowed_values)
        if attr_def and attr_def.attr_type == "ID":
            return f"id-{self.faker.uuid4()[:8]}"
        return self._value_for_name(name)

    def generate_text_value(self, name: str, elem_def: ElementDef | None = None) -> str:
        return self._value_for_name(name, elem_def.doc if elem_def else "")

    def _value_for_name(self, name: str, hint: str = "") -> str:
        lower = name.lower()
        combined = f"{lower} {hint.lower()}"

        if "email" in combined:
            return self.faker.email()
        if re.search(r"\binn\b|inn_", combined):
            return self.faker.numerify(text="##########")
        if "date" in combined or lower.endswith("_date"):
            return str(self.faker.date())
        if lower == "id" or lower.endswith("_id"):
            return str(self.faker.uuid4())
        if "name" in combined:
            return self.faker.name()
        if "phone" in combined or "tel" in combined:
            return self.faker.phone_number()
        if "address" in combined or "addr" in combined:
            return self.faker.address().replace("\n", ", ")
        if "passport" in combined:
            return self.faker.numerify(text="#### ######")
        if "amount" in combined or "sum" in combined or "price" in combined:
            return str(self.faker.pydecimal(left_digits=5, right_digits=2, positive=True))
        if "kladr" in combined:
            return self.faker.numerify(text="###########")
        if "active" in combined or "status" in combined:
            return random.choice(["true", "false", "active", "inactive"])
        if lower in ("title", "label", "description", "comment"):
            return self.faker.sentence(nb_words=4)
        return self.faker.word()


def populate_with_faker(
    xml_text: str,
    schema: DTDSchema,
    locale: str = _DEFAULT_LOCALE,
    *,
    fill_empty_only: bool = False,
    protected_attrs: ProtectedAttrs = frozenset(),
) -> str:
    """Populate an XML document using Smart Faker."""
    return FakerService(locale=locale).populate_xml(
        xml_text,
        schema,
        fill_empty_only=fill_empty_only,
        protected_attrs=protected_attrs,
    )
