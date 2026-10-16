"""Catalog of personal-data categories understood by the anonymizer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    id: str
    label: str
    group: str


CATEGORIES: tuple[Category, ...] = (
    # Person
    Category("person_full", "ФИО целиком", "Персональные данные"),
    Category("person_last", "Фамилия", "Персональные данные"),
    Category("person_first", "Имя", "Персональные данные"),
    Category("person_middle", "Отчество", "Персональные данные"),
    Category("birth_date", "Дата рождения", "Персональные данные"),
    # Documents / identifiers
    Category("inn", "ИНН (10 или 12 цифр)", "Документы и идентификаторы"),
    Category("snils", "СНИЛС", "Документы и идентификаторы"),
    Category("passport_full", "Паспорт: серия и номер вместе", "Документы и идентификаторы"),
    Category("passport_series", "Паспорт: серия", "Документы и идентификаторы"),
    Category("passport_number", "Паспорт: номер", "Документы и идентификаторы"),
    Category("passport_unit_code", "Паспорт: код подразделения", "Документы и идентификаторы"),
    Category("passport_issuer", "Паспорт: кем выдан", "Документы и идентификаторы"),
    Category("doc_date", "Дата документа/события (сдвиг)", "Документы и идентификаторы"),
    Category("kpp", "КПП", "Документы и идентификаторы"),
    Category("ogrn", "ОГРН / ОГРНИП", "Документы и идентификаторы"),
    # Contacts
    Category("phone", "Телефон", "Контакты"),
    Category("email", "Email", "Контакты"),
    # Address
    Category("address_full", "Адрес (строкой)", "Адреса"),
    Category("postcode", "Почтовый индекс", "Адреса"),
    Category("city", "Город", "Адреса"),
    Category("street", "Улица", "Адреса"),
    Category("building", "Дом, корпус, квартира", "Адреса"),
    # Bank
    Category("account_number", "Номер счёта (20 цифр)", "Банковские реквизиты"),
    Category("bic", "БИК", "Банковские реквизиты"),
    Category("card_number", "Номер карты", "Банковские реквизиты"),
    # Organisations / other
    Category("org_name", "Название организации / банка", "Организации и прочее"),
    Category("free_text", "Свободный текст (поиск ПДн внутри)", "Организации и прочее"),
    Category(
        "format_preserving",
        "Любой идентификатор (сохранить формат)",
        "Организации и прочее",
    ),
)

CATEGORY_IDS: frozenset[str] = frozenset(c.id for c in CATEGORIES)
CATEGORY_BY_ID: dict[str, Category] = {c.id: c for c in CATEGORIES}


def is_valid_category(category: str | None) -> bool:
    return bool(category) and category in CATEGORY_IDS


def category_label(category: str | None) -> str:
    if not category:
        return ""
    cat = CATEGORY_BY_ID.get(category)
    return cat.label if cat else category
