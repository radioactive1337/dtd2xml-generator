"""Deterministic, format-preserving fake data for anonymization.

Every fake is derived from ``HMAC(key, kind + normalized original)``: the same
original value always yields the same fake for a given key (so one person or
account stays consistent across the whole document), but the original cannot
be recovered without the key. Plain hashes are deliberately not used -- the
space of INNs or SNILS numbers is small enough to brute-force.

Generated values keep the shape of the original (separators, length, letter
case) and carry valid check digits where the real identifier has them (INN,
SNILS, OGRN, bank account key, BIC tail, card Luhn).
"""

from __future__ import annotations

import hashlib
import hmac
import random
import re
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Dictionaries
# ---------------------------------------------------------------------------

_MALE_FIRST_PATRONYMIC: tuple[tuple[str, str], ...] = (
    ("Александр", "Александрович"), ("Сергей", "Сергеевич"), ("Иван", "Иванович"),
    ("Дмитрий", "Дмитриевич"), ("Андрей", "Андреевич"), ("Алексей", "Алексеевич"),
    ("Михаил", "Михайлович"), ("Николай", "Николаевич"), ("Павел", "Павлович"),
    ("Владимир", "Владимирович"), ("Олег", "Олегович"), ("Виктор", "Викторович"),
    ("Игорь", "Игоревич"), ("Юрий", "Юрьевич"), ("Евгений", "Евгеньевич"),
    ("Максим", "Максимович"), ("Артём", "Артёмович"), ("Роман", "Романович"),
    ("Антон", "Антонович"), ("Константин", "Константинович"), ("Василий", "Васильевич"),
    ("Пётр", "Петрович"), ("Григорий", "Григорьевич"), ("Денис", "Денисович"),
    ("Борис", "Борисович"), ("Валерий", "Валерьевич"), ("Анатолий", "Анатольевич"),
    ("Геннадий", "Геннадьевич"), ("Станислав", "Станиславович"), ("Леонид", "Леонидович"),
)
_FEMALE_FIRST: tuple[str, ...] = (
    "Анна", "Мария", "Елена", "Ольга", "Наталья", "Татьяна", "Ирина", "Светлана",
    "Екатерина", "Юлия", "Анастасия", "Ксения", "Дарья", "Людмила", "Галина",
    "Марина", "Оксана", "Алла", "Виктория", "Вера", "Надежда", "Любовь", "Нина",
    "Лариса", "Полина", "Алина", "Валентина", "Яна", "Евгения", "Тамара",
)
_MALE_SURNAMES: tuple[str, ...] = (
    "Иванов", "Петров", "Сидоров", "Смирнов", "Кузнецов", "Попов", "Васильев",
    "Соколов", "Михайлов", "Новиков", "Фёдоров", "Морозов", "Волков", "Алексеев",
    "Лебедев", "Семёнов", "Егоров", "Павлов", "Козлов", "Степанов", "Николаев",
    "Орлов", "Андреев", "Макаров", "Никитин", "Захаров", "Зайцев", "Соловьёв",
    "Борисов", "Яковлев", "Григорьев", "Романов", "Воробьёв", "Сергеев", "Кузьмин",
    "Фролов", "Александров", "Дмитриев", "Королёв", "Гусев", "Киселёв", "Ильин",
    "Максимов", "Поляков", "Сорокин", "Виноградов", "Ковалёв", "Белов", "Медведев",
    "Антонов",
)
# First names that look feminine by their ending but are masculine.
_MALE_A_NAMES = frozenset({"никита", "илья", "лука", "кузьма", "фома", "данила", "савва", "гаврила"})

_COMPANY_NAMES: tuple[str, ...] = (
    "Альфа-Трейд", "Вектор", "Северный путь", "Горизонт", "Меридиан", "Ньютон",
    "Прогресс-Сервис", "Стройинвест", "Таврида", "Орион", "Квант", "Зенит",
    "Лидер-М", "Рассвет", "Эверест", "Атлант", "Гранит", "Дельта-Консалт", "Заря",
    "Импульс", "Кристалл", "Маяк", "Навигатор", "Олимп", "Пульсар", "Радуга",
    "Сириус", "Титан", "Урал-Снаб", "Фаворит", "Центр-Плюс", "Элемент", "Юпитер",
    "Ямал-Трейд", "Балтика-Групп", "Волна", "Ермак", "Звезда-М", "Исток", "Кедр",
)
_CITIES: tuple[str, ...] = (
    "Тверь", "Тула", "Рязань", "Калуга", "Омск", "Томск", "Пермь", "Самара",
    "Казань", "Уфа", "Липецк", "Курск", "Брянск", "Орёл", "Ярославль", "Кострома",
    "Саратов", "Пенза", "Ульяновск", "Чебоксары", "Иваново", "Владимир", "Смоленск",
    "Белгород", "Воронеж",
)
_STREETS: tuple[str, ...] = (
    "Ленина", "Мира", "Советская", "Гагарина", "Пушкина", "Садовая", "Школьная",
    "Центральная", "Молодёжная", "Лесная", "Новая", "Набережная", "Заводская",
    "Парковая", "Кирова", "Победы", "Строителей", "Октябрьская", "Первомайская",
    "Комсомольская", "Солнечная", "Береговая", "Зелёная", "Юбилейная",
)
_REGIONS: tuple[str, ...] = (
    "Московская область", "Ленинградская область", "Свердловская область",
    "Республика Татарстан", "Краснодарский край", "Новосибирская область",
    "Самарская область", "Нижегородская область",
)
_REGION_CODES: tuple[str, ...] = ("77", "78", "50", "16", "66", "54", "02", "23", "52", "63")

_CYR_UPPER = "АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЭЮЯ"
_CYR_LOWER = "абвгдежзиклмнопрстуфхцчшэюя"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def mask_value(value: str) -> str:
    """Human-safe preview of a real value: ``Иванов`` -> ``И***в``."""
    text = (value or "").strip()
    if not text:
        return ""
    if len(text) <= 2:
        return "*" * len(text)
    if len(text) <= 4:
        return text[0] + "*" * (len(text) - 1)
    return text[0] + "*" * min(len(text) - 2, 5) + text[-1]


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _norm_text(value: str) -> str:
    return " ".join((value or "").split()).casefold().replace("ё", "е")


def _rand_digits(rng: random.Random, n: int, *, nonzero_first: bool = False) -> str:
    if n <= 0:
        return ""
    digits = [str(rng.randrange(10)) for _ in range(n)]
    if nonzero_first:
        digits[0] = str(rng.randrange(1, 10))
    return "".join(digits)


def _fill_template(template: str, digits: str) -> str:
    """Put *digits* into the digit positions of *template*, keeping separators."""
    it = iter(digits)
    out: list[str] = []
    for ch in template:
        out.append(next(it, ch) if ch.isdigit() else ch)
    return "".join(out)


def _match_case(original: str, fake: str) -> str:
    if len(original) > 1 and original.isupper():
        return fake.upper()
    if original.islower():
        return fake.lower()
    return fake


def _pick(rng: random.Random, items: tuple[str, ...], avoid: str = "") -> str:
    idx = rng.randrange(len(items))
    pick = items[idx]
    if avoid and _norm_text(pick) == _norm_text(avoid):
        pick = items[(idx + 1) % len(items)]
    return pick


# ---------------------------------------------------------------------------
# Check digits
# ---------------------------------------------------------------------------


def inn10_check(first9: str) -> str:
    w = (2, 4, 10, 3, 5, 9, 4, 6, 8)
    return str(sum(int(d) * k for d, k in zip(first9, w, strict=True)) % 11 % 10)


def inn12_checks(first10: str) -> str:
    w11 = (7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
    n11 = sum(int(d) * k for d, k in zip(first10, w11, strict=True)) % 11 % 10
    w12 = (3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8)
    n12 = sum(int(d) * k for d, k in zip(first10 + str(n11), w12, strict=True)) % 11 % 10
    return f"{n11}{n12}"


def is_valid_inn(value: str) -> bool:
    d = _digits_only(value)
    if len(d) == 10:
        return d[9] == inn10_check(d[:9])
    if len(d) == 12:
        return d[10:] == inn12_checks(d[:10])
    return False


def snils_control(first9: str) -> str:
    total = sum(int(d) * (9 - i) for i, d in enumerate(first9))
    if total < 100:
        control = total
    elif total in (100, 101):
        control = 0
    else:
        control = total % 101
        if control in (100, 101):
            control = 0
    return f"{control:02d}"


def is_valid_snils(value: str) -> bool:
    d = _digits_only(value)
    return len(d) == 11 and d[9:] == snils_control(d[:9])


def luhn_check_digit(body: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(body)):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return str((10 - total % 10) % 10)


def account_key(bic: str, account20: str) -> str:
    """Control digit of a 20-digit settlement account for the bank's *bic*."""
    seq = bic[-3:] + account20[:8] + "0" + account20[9:]
    weights = (7, 1, 3)
    total = sum((int(d) * weights[i % 3]) % 10 for i, d in enumerate(seq))
    return str((total % 10) * 3 % 10)


def is_valid_account(bic: str, account: str) -> bool:
    d = _digits_only(account)
    b = _digits_only(bic)
    return len(d) == 20 and len(b) == 9 and d[8] == account_key(b, d)


def ogrn_check(body: str) -> str:
    n = int(body)
    return str(n % (11 if len(body) == 12 else 13) % 10)


# ---------------------------------------------------------------------------
# Names
# ---------------------------------------------------------------------------

_PATRONYMIC_RE = re.compile(r"(ович|евич|ьич|ич|овна|евна|ична|инична|кызы|оглы)$", re.I)
_INITIALS_RE = re.compile(r"^[А-ЯЁA-Z]\.(?:\s?[А-ЯЁA-Z]\.)?$")


def is_patronymic(token: str) -> bool:
    return bool(_PATRONYMIC_RE.search(token.strip()))


def detect_gender(role: str, token: str) -> str | None:
    """Best-effort gender ('m' / 'f') of a name token, ``None`` when unknown."""
    t = token.strip().casefold().replace("ё", "е")
    if not t:
        return None
    if role == "middle":
        if t.endswith(("вна", "чна", "кызы")):
            return "f"
        if t.endswith(("ич", "оглы")):
            return "m"
        return None
    if role == "last":
        if t.endswith(("ова", "ева", "ина", "ына", "ая", "ская", "цкая")):
            return "f"
        if t.endswith(("ов", "ев", "ин", "ын", "ский", "цкий", "ой", "ий", "ый")):
            return "m"
        return None
    if role == "first":
        if t in _MALE_A_NAMES:
            return "m"
        if t.endswith(("а", "я")):
            return "f"
        return "m"
    return None


def _female_surname(male: str) -> str:
    if male.endswith("ский"):
        return male[:-2] + "ая"
    return male + "а"


def _female_patronymic(male: str) -> str:
    for suffix, repl in (("ович", "овна"), ("евич", "евна"), ("ьич", "ьична")):
        if male.endswith(suffix):
            return male[: -len(suffix)] + repl
    return male


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

_DATE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<!\d)(\d{2})\.(\d{2})\.(\d{4})(?!\d)"), "dmy."),
    (re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"), "ymd-"),
    (re.compile(r"(?<!\d)(\d{2})/(\d{2})/(\d{4})(?!\d)"), "dmy/"),
)


def shift_date_text(value: str, rng: random.Random, min_days: int, max_days: int) -> str | None:
    """Shift the first date found in *value* by a deterministic offset, same format."""
    for pattern, kind in _DATE_PATTERNS:
        match = pattern.search(value)
        if not match:
            continue
        a, b, c = (int(g) for g in match.groups())
        try:
            current = date(c, b, a) if kind.startswith("dmy") else date(a, b, c)
        except ValueError:
            continue
        offset = rng.randint(min_days, max_days) * rng.choice((-1, 1))
        try:
            shifted = current + timedelta(days=offset)
        except OverflowError:
            continue
        if kind == "dmy.":
            text = f"{shifted.day:02d}.{shifted.month:02d}.{shifted.year:04d}"
        elif kind == "dmy/":
            text = f"{shifted.day:02d}/{shifted.month:02d}/{shifted.year:04d}"
        else:
            text = f"{shifted.year:04d}-{shifted.month:02d}-{shifted.day:02d}"
        return value[: match.start()] + text + value[match.end() :]
    return None


# ---------------------------------------------------------------------------
# Address patterns
# ---------------------------------------------------------------------------

_ADDR_CITY = re.compile(
    r"(?P<p>\b(?:г|город)\.?\s*)(?P<n>[А-ЯЁ][А-Яа-яЁё-]+(?:\s[А-ЯЁ][а-яё-]+)?)"
)
_ADDR_STREET = re.compile(
    r"(?P<p>\b(?:ул|улица|пр-кт|просп|проспект|пер|переулок|ш|шоссе|б-р|бульвар|"
    r"наб|набережная|пл|площадь|проезд)\.?\s+)(?P<n>[А-ЯЁ0-9][А-Яа-яЁё0-9-]*)"
)
_ADDR_HOUSE = re.compile(
    r"(?P<p>\b(?:д|дом|к|корп|корпус|стр|строение|кв|квартира|оф|офис|пом|помещение)"
    r"\.?\s*)(?P<n>\d+[А-Яа-яA-Za-z]?(?:/\d+)?)"
)
_ADDR_REGION = re.compile(
    r"\b(?:[А-ЯЁ][а-яё-]+\s+(?:область|край|округ)|Республика\s+[А-ЯЁ][а-яё-]+|"
    r"[А-ЯЁ][а-яё-]+\s+(?:обл|респ)\.?)"
)
_ADDR_POSTCODE = re.compile(r"(?<!\d)\d{6}(?!\d)")

_ORG_FORM_RE = re.compile(
    r"^\s*(?P<form>ООО|ОАО|ЗАО|ПАО|АО|НКО|ИП|ГУП|МУП|ФГУП|КБ)\b\.?\s*(?P<rest>.*)$", re.S
)
_QUOTED_RE = re.compile(r"[«\"“](?P<inner>[^»\"”]+)[»\"”]")

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class FakeFactory:
    """Produces deterministic fakes for a given secret *key*."""

    def __init__(self, key: bytes) -> None:
        self._key = key
        # last-name (normalized) -> (fake_first, fake_middle) seen in full names,
        # lets "Иванов И.И." follow "Иванов Иван Иванович".
        self.persons: dict[str, tuple[str, str]] = {}

    # -- randomness --------------------------------------------------------

    def rng(self, kind: str, value: str) -> random.Random:
        digest = hmac.new(
            self._key, f"{kind}\x00{value}".encode(), hashlib.sha256
        ).digest()
        return random.Random(int.from_bytes(digest, "big"))

    # -- names -------------------------------------------------------------

    def fake_last(self, token: str) -> str:
        if "-" in token.strip("-"):
            return "-".join(self.fake_last(part) for part in token.split("-") if part)
        rng = self.rng("last", _norm_text(token))
        gender = detect_gender("last", token) or rng.choice(("m", "f"))
        fake = _pick(rng, _MALE_SURNAMES, avoid=token)
        if gender == "f":
            fake = _female_surname(fake)
        return _match_case(token, fake)

    def fake_first(self, token: str) -> str:
        if "-" in token.strip("-"):
            return "-".join(self.fake_first(part) for part in token.split("-") if part)
        rng = self.rng("first", _norm_text(token))
        gender = detect_gender("first", token) or "m"
        if gender == "f":
            fake = _pick(rng, _FEMALE_FIRST, avoid=token)
        else:
            fake = _pick(rng, tuple(m for m, _ in _MALE_FIRST_PATRONYMIC), avoid=token)
        return _match_case(token, fake)

    def fake_middle(self, token: str) -> str:
        rng = self.rng("middle", _norm_text(token))
        gender = detect_gender("middle", token) or rng.choice(("m", "f"))
        male = _pick(rng, tuple(p for _, p in _MALE_FIRST_PATRONYMIC), avoid=token)
        fake = _female_patronymic(male) if gender == "f" else male
        return _match_case(token, fake)

    @staticmethod
    def split_person(value: str) -> list[tuple[str, str]]:
        """Return ``[(token, role)]``; roles: last/first/middle/initials."""
        tokens = value.replace("\u00a0", " ").split()
        names = [t for t in tokens if not _INITIALS_RE.match(t)]
        roles: dict[int, str] = {}
        if len(names) >= 3 and is_patronymic(names[1]) and not is_patronymic(names[2]):
            order = ["first", "middle", "last"]
        elif len(names) == 2 and is_patronymic(names[1]):
            order = ["first", "middle"]
        else:
            order = ["last", "first", "middle"]
        n = 0
        for i, token in enumerate(tokens):
            if _INITIALS_RE.match(token):
                roles[i] = "initials"
            else:
                roles[i] = order[n] if n < len(order) else "middle"
                n += 1
        return [(t, roles[i]) for i, t in enumerate(tokens)]

    def fake_person_full(self, value: str) -> str:
        parts = self.split_person(value)
        last = next((t for t, r in parts if r == "last"), "")
        fake_by_role: dict[str, str] = {}
        out: list[str] = []
        pending_initials: list[int] = []
        for token, role in parts:
            if role == "last":
                fake = self.fake_last(token)
            elif role == "first":
                fake = self.fake_first(token)
            elif role == "middle":
                fake = self.fake_middle(token)
            else:
                pending_initials.append(len(out))
                fake = token
            if role in ("last", "first", "middle"):
                fake_by_role[role] = fake
            out.append(fake)
        if last and ("first" in fake_by_role):
            self.persons[_norm_text(last)] = (
                fake_by_role["first"],
                fake_by_role.get("middle", ""),
            )
        seq = 0  # position among single-letter initial tokens ("И." "И.")
        for idx in pending_initials:
            token = parts[idx][0]
            first = fake_by_role.get("first")
            middle = fake_by_role.get("middle")
            if first is None and last:
                known = self.persons.get(_norm_text(last))
                if known:
                    first, middle = known[0], known[1] or None
            letters = re.findall(r"[А-ЯЁA-Z]", token)
            out[idx] = self._fake_initials(token, last, first, middle, len(letters), seq)
            if len(letters) == 1:
                seq += 1
        return " ".join(out)

    def _fake_initials(
        self,
        token: str,
        last: str,
        first: str | None,
        middle: str | None,
        letter_count: int,
        seq: int,
    ) -> str:
        rng = self.rng("initials", _norm_text(last) + "|" + token)
        if first is None:
            gender = detect_gender("last", last) or "m"
            pool = _FEMALE_FIRST if gender == "f" else tuple(m for m, _ in _MALE_FIRST_PATRONYMIC)
            first = _pick(rng, pool)
        if not middle:
            gender = detect_gender("last", last) or "m"
            male_patr = _pick(rng, tuple(p for _, p in _MALE_FIRST_PATRONYMIC))
            middle = _female_patronymic(male_patr) if gender == "f" else male_patr
        if letter_count >= 2:
            return f"{first[0].upper()}.{middle[0].upper()}."
        return f"{(first if seq == 0 else middle)[0].upper()}."

    # -- numbers / identifiers --------------------------------------------

    def fake_inn(self, value: str) -> str:
        d = _digits_only(value)
        rng = self.rng("inn", d)
        region = d[:2] if len(d) >= 2 and d[:2].isdigit() else rng.choice(_REGION_CODES)
        if len(d) == 10:
            first9 = region + _rand_digits(rng, 7)
            new = first9 + inn10_check(first9)
        elif len(d) == 12:
            first10 = region + _rand_digits(rng, 8)
            new = first10 + inn12_checks(first10)
        else:
            return self.fake_format_preserving(value)
        if new == d:
            new = new[:2] + _rand_digits(rng, len(new) - 2)
            new = new[: len(d) - (1 if len(d) == 10 else 2)]
            new = new + (inn10_check(new) if len(d) == 10 else inn12_checks(new))
        return _fill_template(value, new)

    def fake_snils(self, value: str) -> str:
        d = _digits_only(value)
        if len(d) != 11:
            return self.fake_format_preserving(value)
        rng = self.rng("snils", d)
        body = _rand_digits(rng, 9, nonzero_first=True)
        return _fill_template(value, body + snils_control(body))

    def fake_kpp(self, value: str) -> str:
        d = _digits_only(value)
        if len(d) != 9:
            return self.fake_format_preserving(value)
        rng = self.rng("kpp", d)
        return _fill_template(value, _rand_digits(rng, 4, nonzero_first=True) + d[4:6] + _rand_digits(rng, 3))

    def fake_ogrn(self, value: str) -> str:
        d = _digits_only(value)
        if len(d) not in (13, 15):
            return self.fake_format_preserving(value)
        rng = self.rng("ogrn", d)
        body = d[0] + _rand_digits(rng, len(d) - 2)
        return _fill_template(value, body + ogrn_check(body))

    def fake_bic(self, value: str) -> str:
        d = _digits_only(value)
        if len(d) != 9:
            return self.fake_format_preserving(value)
        rng = self.rng("bic", d)
        tail = f"{rng.randint(50, 999):03d}"
        return _fill_template(value, d[:2] + _rand_digits(rng, 4) + tail)

    def fake_account(self, value: str, bic_value: str | None = None) -> str:
        d = _digits_only(value)
        if len(d) != 20:
            return self.fake_format_preserving(value)
        rng = self.rng("account", d)
        # Keep the account type and currency (first 8 digits): not identifying.
        body = d[:8] + "0" + _rand_digits(rng, 4) + _rand_digits(rng, 7)
        bic_digits = _digits_only(bic_value or "")
        if len(bic_digits) != 9:
            bic_digits = "04" + _rand_digits(rng, 4) + f"{rng.randint(50, 999):03d}"
        new = body[:8] + account_key(bic_digits, body) + body[9:]
        return _fill_template(value, new)

    def fake_card(self, value: str) -> str:
        d = _digits_only(value)
        if not 13 <= len(d) <= 19:
            return self.fake_format_preserving(value)
        rng = self.rng("card", d)
        body = d[:6] + _rand_digits(rng, len(d) - 7)
        return _fill_template(value, body + luhn_check_digit(body))

    def fake_digits(self, value: str, kind: str) -> str:
        d = _digits_only(value)
        if not d:
            return self.fake_format_preserving(value)
        rng = self.rng(kind, d)
        return _fill_template(value, _rand_digits(rng, len(d), nonzero_first=d[0] != "0"))

    def fake_phone(self, value: str) -> str:
        d = _digits_only(value)
        rng = self.rng("phone", d)
        if len(d) == 11 and d[0] in "78":
            new = d[0] + "9" + _rand_digits(rng, 9)
        elif len(d) == 10:
            new = "9" + _rand_digits(rng, 9)
        else:
            return self.fake_format_preserving(value)
        return _fill_template(value, new)

    def fake_email(self, value: str) -> str:
        rng = self.rng("email", value.strip().casefold())
        return f"user{rng.randrange(16**6):06x}@example.com"

    def fake_date(self, value: str, *, birth: bool) -> str:
        rng = self.rng("birth" if birth else "date", value.strip())
        lo, hi = (60, 700) if birth else (3, 400)
        shifted = shift_date_text(value, rng, lo, hi)
        return shifted if shifted is not None else self.fake_format_preserving(value)

    def fake_format_preserving(self, value: str) -> str:
        rng = self.rng("fp", value)
        out: list[str] = []
        for ch in value:
            if ch.isdigit():
                out.append(str(rng.randrange(10)))
            elif ch in _CYR_UPPER or ch == "Ё":
                out.append(rng.choice(_CYR_UPPER))
            elif ch in _CYR_LOWER or ch == "ё":
                out.append(rng.choice(_CYR_LOWER))
            elif "A" <= ch <= "Z":
                out.append(chr(rng.randrange(65, 91)))
            elif "a" <= ch <= "z":
                out.append(chr(rng.randrange(97, 123)))
            else:
                out.append(ch)
        if len(out) and out == list(value):
            return value
        return "".join(out)

    # -- organisations / addresses ----------------------------------------

    def fake_org(self, value: str) -> str:
        match = _ORG_FORM_RE.match(value)
        if match and match.group("form") == "ИП":
            rest = match.group("rest").strip()
            return f"ИП {self.fake_person_full(rest)}" if rest else value
        form = match.group("form") if match else ""
        rest = match.group("rest") if match else value
        rng = self.rng("org", _norm_text(value))
        name = _pick(rng, _COMPANY_NAMES, avoid=value)
        quoted = _QUOTED_RE.search(rest)
        if quoted:
            fake_rest = rest[: quoted.start("inner")] + name + rest[quoted.end("inner") :]
        elif form:
            fake_rest = f"«{name}»"
        else:
            fake_rest = name
        return f"{form} {fake_rest}".strip()

    def fake_city(self, value: str) -> str:
        match = _ADDR_CITY.search(value)
        rng = self.rng("city", _norm_text(match.group("n") if match else value))
        if match:
            name = _pick(rng, _CITIES, avoid=match.group("n"))
            return value[: match.start("n")] + name + value[match.end("n") :]
        return _pick(rng, _CITIES, avoid=value)

    def fake_street(self, value: str) -> str:
        match = _ADDR_STREET.search(value)
        rng = self.rng("street", _norm_text(match.group("n") if match else value))
        if match:
            name = _pick(rng, _STREETS, avoid=match.group("n"))
            return value[: match.start("n")] + name + value[match.end("n") :]
        return _pick(rng, _STREETS, avoid=value)

    def fake_address(self, value: str) -> str:
        text = _ADDR_POSTCODE.sub(
            lambda m: _rand_digits(self.rng("postcode", m.group(0)), 6, nonzero_first=True),
            value,
        )
        text = _ADDR_REGION.sub(
            lambda m: _pick(self.rng("region", _norm_text(m.group(0))), _REGIONS, avoid=m.group(0)),
            text,
        )
        text = _ADDR_CITY.sub(
            lambda m: m.group("p")
            + _pick(self.rng("city", _norm_text(m.group("n"))), _CITIES, avoid=m.group("n")),
            text,
        )
        text = _ADDR_STREET.sub(
            lambda m: m.group("p")
            + _pick(self.rng("street", _norm_text(m.group("n"))), _STREETS, avoid=m.group("n")),
            text,
        )
        text = _ADDR_HOUSE.sub(
            lambda m: m.group("p") + self.fake_format_preserving(m.group("n")), text
        )
        return text

    def fake_passport_issuer(self, value: str) -> str:
        rng = self.rng("issuer", _norm_text(value))
        return f"ОУФМС России по г. {_pick(rng, _CITIES)}"

    # -- dispatch ----------------------------------------------------------

    def fake(self, category: str, value: str, *, bic_hint: str | None = None) -> str:
        """Return the fake for *value* of *category* (never equal to *value* if avoidable)."""
        if category == "person_full":
            return self.fake_person_full(value)
        if category == "person_last":
            return self.fake_last(value)
        if category == "person_first":
            return self.fake_first(value)
        if category == "person_middle":
            return self.fake_middle(value)
        if category == "birth_date":
            return self.fake_date(value, birth=True)
        if category == "doc_date":
            return self.fake_date(value, birth=False)
        if category == "inn":
            return self.fake_inn(value)
        if category == "snils":
            return self.fake_snils(value)
        if category in ("passport_full", "passport_series", "passport_number", "passport_unit_code"):
            return self.fake_digits(value, category)
        if category == "passport_issuer":
            return self.fake_passport_issuer(value)
        if category == "kpp":
            return self.fake_kpp(value)
        if category == "ogrn":
            return self.fake_ogrn(value)
        if category == "phone":
            return self.fake_phone(value)
        if category == "email":
            return self.fake_email(value)
        if category == "address_full":
            return self.fake_address(value)
        if category == "postcode":
            return self.fake_digits(value, "postcode")
        if category == "city":
            return self.fake_city(value)
        if category == "street":
            return self.fake_street(value)
        if category == "building":
            return self.fake_format_preserving(value)
        if category == "account_number":
            return self.fake_account(value, bic_hint)
        if category == "bic":
            return self.fake_bic(value)
        if category == "card_number":
            return self.fake_card(value)
        if category == "org_name":
            return self.fake_org(value)
        # format_preserving, free_text (when a whole value is targeted) and unknown.
        return self.fake_format_preserving(value)


def looks_like_email(value: str) -> bool:
    return bool(_EMAIL_RE.fullmatch((value or "").strip()))
