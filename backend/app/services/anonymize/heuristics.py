"""Heuristics that help the review queue: is a value suspicious, and what is it?

Heuristics never change a document on their own. They only (a) decide whether an
unclassified value needs a human look (``is_suspicious``) and (b) propose a
category (``guess_category``) shown as a suggestion in the queue.
"""

from __future__ import annotations

import re

from app.services.anonymize.generators import is_valid_inn, luhn_check_digit

_TOKEN_SPLIT_CAMEL = re.compile(r"([a-z0-9])([A-Z])")
_TOKEN_RE = re.compile(r"[A-Za-z]+|\d+|[А-Яа-яЁё]+")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SNILS_RE = re.compile(r"^\d{3}-\d{3}-\d{3}[ -]\d{2}$")
_PHONE_RE = re.compile(r"^(?:\+7|7|8)[\s(\-]*\d{3}[\s)\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}$")
_DATE_RE = re.compile(
    r"^(?:\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2}(?:[T ][\d:.+Zz-]*)?|\d{2}/\d{2}/\d{4})$"
)
_CYR_WORD_RE = re.compile(r"^[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?$")
_PATRONYMIC_END = re.compile(r"(ович|евич|ьич|овна|евна|ична|инична)$", re.I)

_SAFE_UPPER_ID = re.compile(r"^[A-Z][A-Z0-9_.:\-]{0,30}$")
_SAFE_LOWER_ID = re.compile(r"^[a-z][A-Za-z0-9_.:\-]{0,40}$")
_SAFE_SHORT_INT = re.compile(r"^\d{1,5}$")
_LONG_DIGITS = re.compile(r"\d{6,}")


def _tokens(name: str) -> set[str]:
    spaced = _TOKEN_SPLIT_CAMEL.sub(r"\1 \2", name or "")
    return {t.lower() for t in _TOKEN_RE.findall(spaced)}


def _name_category(tokens: set[str]) -> str | None:
    t = tokens
    if not t:
        return None
    if "snils" in t or "снилс" in t:
        return "snils"
    if "inn" in t or "инн" in t:
        return "inn"
    if "kpp" in t or "кпп" in t:
        return "kpp"
    if t & {"ogrn", "ogrnip", "огрн"}:
        return "ogrn"
    if t & {"bic", "bik", "бик"}:
        return "bic"
    if t & {"email", "mail", "почта"}:
        return "email"
    if t & {"phone", "tel", "telephone", "mobile", "msisdn", "fax", "телефон"}:
        return "phone"
    if t & {"passport", "pasport", "паспорт"}:
        if t & {"series", "seria", "серия"}:
            return "passport_series"
        if t & {"number", "num", "no", "номер"}:
            return "passport_number"
        if "unit" in t or "подразделения" in t:
            return "passport_unit_code"
        if t & {"issuer", "issued", "vydan"}:
            return "passport_issuer"
        return "passport_full"
    if {"unit", "code"} <= t:
        return "passport_unit_code"
    if t & {"birth", "dob", "birthdate", "bdate", "рождения"}:
        return "birth_date"
    if t & {"surname", "familiya", "family", "фамилия"} or {"last", "name"} <= t or "lastname" in t:
        return "person_last"
    if t & {"patronymic", "otchestvo", "отчество", "middlename"} or {"middle", "name"} <= t:
        return "person_middle"
    if {"first", "name"} <= t or t & {"firstname", "givenname", "имя"} or {"given", "name"} <= t:
        return "person_first"
    if t & {"fio", "фио"} or {"full", "name"} <= t or {"client", "name"} <= t or {"person", "name"} <= t:
        return "person_full"
    if t & {"card", "pan"} and t & {"number", "num", "no"}:
        return "card_number"
    if t & {"account", "acc", "schet", "rs"} and (t & {"number", "num", "no"} or len(t) == 1):
        return "account_number"
    if t & {"postcode", "zip", "postal", "индекс"}:
        return "postcode"
    if t & {"address", "addr", "adres", "адрес"}:
        return "address_full"
    if t & {"city", "town", "locality", "gorod", "город"}:
        return "city"
    if t & {"street", "ulitsa", "улица"}:
        return "street"
    if t & {"house", "building", "flat", "apartment", "korpus", "kvartira", "дом", "квартира"}:
        return "building"
    if t & {"org", "organization", "organisation", "company", "bank"} and "name" in t:
        return "org_name"
    if "issue" in t and t & {"date", "dt"}:
        return "doc_date"
    return None


def _value_category(value: str, name_cat: str | None) -> str | None:
    v = value.strip()
    if _EMAIL_RE.match(v):
        return "email"
    digits = re.sub(r"\D", "", v)
    if _SNILS_RE.match(v):
        return "snils"
    if re.fullmatch(r"\d{20}", v):
        return "account_number"
    if re.fullmatch(r"\d{13,19}", v) and luhn_check_digit(v[:-1]) == v[-1] and len(v) >= 15:
        return "card_number"
    if re.fullmatch(r"04\d{7}", v):
        return "bic"
    if re.fullmatch(r"\d{10}|\d{12}", v) and is_valid_inn(v):
        return "inn"
    if _PHONE_RE.match(v) and len(digits) == 11:
        return "phone"
    if _DATE_RE.match(v):
        return "birth_date" if name_cat == "birth_date" else "doc_date"
    words = v.split()
    if (
        len(words) == 3
        and all(_CYR_WORD_RE.match(w) for w in words)
        and _PATRONYMIC_END.search(words[2])
    ):
        return "person_full"
    return None


def guess_category(attr: str, value: str, name: str = "") -> tuple[str | None, str]:
    """Return ``(suggested_category, reason)``; both empty when nothing fits."""
    name_cat = _name_category(_tokens(attr)) or _name_category(_tokens(name))
    value_cat = _value_category(value, name_cat)
    # A value-shape match is stronger than a name hint (digits tell more than a name).
    if value_cat and value_cat not in ("doc_date",):
        return value_cat, "по виду значения"
    if name_cat:
        return name_cat, "по имени поля"
    if value_cat:
        return value_cat, "по виду значения"
    return None, ""


def is_suspicious(value: str) -> bool:
    """True when an unclassified *value* should block a "clean" status.

    Conservative on purpose: only short Latin identifiers, flags and small
    integers are treated as safe; everything else (Cyrillic text, long digit
    runs, dates, e-mail, capitalized words) needs a decision.
    """
    v = (value or "").strip()
    if not v:
        return False
    if v.lower() in {"true", "false"}:
        return False
    if _SAFE_SHORT_INT.match(v):
        return False
    if _SAFE_UPPER_ID.match(v) or _SAFE_LOWER_ID.match(v):
        return bool(_LONG_DIGITS.search(v))
    return True
