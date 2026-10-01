"""Fake-data generators: shape, check digits, determinism."""

from __future__ import annotations

import re

from app.services.anonymize.generators import (
    FakeFactory,
    inn10_check,
    inn12_checks,
    is_valid_account,
    is_valid_inn,
    is_valid_snils,
    luhn_check_digit,
    mask_value,
    snils_control,
)

KEY = b"k" * 32


def _inn12(base10: str = "5001007322") -> str:
    return base10 + inn12_checks(base10)


def _inn10(base9: str = "500100732") -> str:
    return base9 + inn10_check(base9)


def test_inn_keeps_length_and_is_valid():
    gen = FakeFactory(KEY)
    person = _inn12()
    org = _inn10()
    assert is_valid_inn(person) and is_valid_inn(org)

    fake_person = gen.fake("inn", person)
    fake_org = gen.fake("inn", org)

    assert len(fake_person) == 12 and is_valid_inn(fake_person) and fake_person != person
    assert len(fake_org) == 10 and is_valid_inn(fake_org) and fake_org != org


def test_snils_valid_and_template_preserved():
    gen = FakeFactory(KEY)
    body = "112233445"
    original = f"{body[:3]}-{body[3:6]}-{body[6:]} {snils_control(body)}"
    assert is_valid_snils(original)

    fake = gen.fake("snils", original)

    assert re.fullmatch(r"\d{3}-\d{3}-\d{3} \d{2}", fake)
    assert is_valid_snils(fake) and fake != original


def test_account_key_valid_for_given_bic():
    gen = FakeFactory(KEY)
    bic = "044525225"
    original = "40817810099910004312"

    fake = gen.fake("account_number", original, bic_hint=bic)

    assert len(fake) == 20 and fake != original
    assert fake[:8] == original[:8]
    assert is_valid_account(bic, fake)


def test_bic_shape():
    fake = FakeFactory(KEY).fake("bic", "044525225")
    assert re.fullmatch(r"04\d{4}\d{3}", fake)
    assert int(fake[-3:]) >= 50


def test_card_luhn_valid():
    original = "411111111111111" + luhn_check_digit("411111111111111")
    fake = FakeFactory(KEY).fake("card_number", original)
    assert len(fake) == len(original) and fake != original
    assert luhn_check_digit(fake[:-1]) == fake[-1]


def test_deterministic_per_key_and_differs_across_keys():
    value = "Иванов Иван Иванович"
    first = FakeFactory(KEY).fake("person_full", value)
    again = FakeFactory(KEY).fake("person_full", value)
    other = FakeFactory(b"z" * 32).fake("person_full", value)
    assert first == again
    assert first != value
    assert other != value


def test_person_gender_consistency():
    gen = FakeFactory(KEY)
    fake = gen.fake("person_full", "Петрова Анна Сергеевна").split()
    assert fake[0].endswith(("а", "ая"))
    assert fake[2].endswith("на")

    fake_m = gen.fake("person_full", "Петров Андрей Сергеевич").split()
    assert not fake_m[0].endswith("а")
    assert fake_m[2].endswith("ич")


def test_person_case_preserved():
    fake = FakeFactory(KEY).fake("person_last", "ИВАНОВ")
    assert fake.isupper()


def test_initials_follow_registered_person():
    gen = FakeFactory(KEY)
    full = gen.fake("person_full", "Иванов Иван Иванович").split()
    short = gen.fake("person_full", "Иванов И.И.").split()
    assert short[1] == f"{full[1][0]}.{full[2][0]}."


def test_phone_format_preserved():
    fake = FakeFactory(KEY).fake("phone", "+7 (916) 123-45-67")
    assert re.fullmatch(r"\+7 \(\d{3}\) \d{3}-\d{2}-\d{2}", fake)
    assert fake != "+7 (916) 123-45-67"


def test_email_is_valid_and_synthetic():
    fake = FakeFactory(KEY).fake("email", "ivan@bank.ru")
    assert re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", fake)
    assert fake.endswith("@example.com")


def test_dates_keep_format():
    gen = FakeFactory(KEY)
    ru = gen.fake("birth_date", "01.02.1980")
    iso = gen.fake("doc_date", "2020-05-17")
    assert re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", ru) and ru != "01.02.1980"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso) and iso != "2020-05-17"


def test_passport_template_preserved():
    gen = FakeFactory(KEY)
    assert re.fullmatch(r"\d{2} \d{2} \d{6}", gen.fake("passport_full", "45 10 123456"))
    assert re.fullmatch(r"\d{3}-\d{3}", gen.fake("passport_unit_code", "770-001"))


def test_org_keeps_legal_form_and_quotes():
    fake = FakeFactory(KEY).fake("org_name", 'ООО «Ромашка»')
    assert fake.startswith("ООО «") and fake.endswith("»")
    assert "Ромашка" not in fake


def test_address_replaced_but_shape_kept():
    original = "123456, г. Москва, ул. Ленина, д. 5, кв. 12"
    fake = FakeFactory(KEY).fake("address_full", original)
    assert "Москва" not in fake
    assert "123456" not in fake
    assert "г. " in fake and "ул. " in fake and "д. " in fake and "кв. " in fake


def test_mask_value():
    assert mask_value("") == ""
    assert mask_value("ab") == "**"
    assert mask_value("Иванов") == "И****в"
    assert "12345678" not in mask_value("12345678901")
