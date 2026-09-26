"""Decide whether a piece of Evidence supports a Claim (ADR-0003: doubt resolves to Supported)."""

from __future__ import annotations

import re
from decimal import Decimal

from ._extract import DOLLAR_FAMILY, YEN_FAMILY, Fact


def _same_currency(a: str | None, b: str | None) -> bool:
    """Equal codes, or a bare "$"/"¥" beside any currency written with that symbol."""
    if a == b or a is None or b is None:  # 元/块 name no particular currency
        return True
    return any(generic in (a, b) and a in family and b in family
               for generic, family in (("$", DOLLAR_FAMILY), ("¥", YEN_FAMILY)))


def _date_matches(claim: str, evidence: str) -> bool:
    """Every part the Claim states must be stated, identically, by the Evidence."""
    return all(c == "X" or c == e for c, e in zip(claim, evidence))


def _phone_matches(claim: str, evidence: str) -> bool:
    """Equal digits, allowing a country code or trunk 0 on either side."""
    a, b = claim.lstrip("0"), evidence.lstrip("0")
    if len(b) >= len(a):
        return len(a) >= 7 and b.endswith(a)
    return len(b) >= 9 and a.endswith(b)  # the Claim added a country code to a full national number


_LONGEST_DIGITS = 20
"""Digits a quantity may have to be read as a digit string (phone, account); no phone number has more."""


def _digits(fact: Fact) -> str | None:
    """The digit string of a Fact that could be a phone number stored another way."""
    if fact.kind == "phone":
        return fact.value
    if fact.kind == "identifier" and fact.value.isdigit():
        return fact.value
    if fact.kind == "quantity" and fact.value == fact.value.to_integral_value() and fact.value.adjusted() < _LONGEST_DIGITS:
        return str(int(fact.value))  # 1.2 million is "1200000", never "1200000.0"
    return None


_PATH_NUMBER = re.compile(
    r"/(?:pull|pulls|issues?|merge_requests|orders?|tickets?|invoices?|cases?|runs|jobs|builds|deployments?|"
    r"reservations?|bookings?|shipments?)/([0-9]{1,20})(?=[/?#]|$)", re.I)
"""The ID of a resource in its URL (".../pull/3337", "/orders/48213"); not an image size or a page number."""


def _path_numbers(url: str) -> list[str]:
    return _PATH_NUMBER.findall(url)


_GIT_HASH = re.compile(r"(?=[0-9]*[a-f])[0-9a-f]{7,40}")
_LONG_HASH = 12
"""A Source hash long enough to be shortened: git's full hash, not an 8-character order code."""


def _is_long_hash(text: str) -> bool:
    return len(text) >= _LONG_HASH and bool(_GIT_HASH.fullmatch(text))
"""A git commit hash, as git writes it (lowercase, with a letter): its short and full forms name one commit."""


def _trailing_digits(fact: Fact) -> str | None:
    """The digits a Fact's value ends with: 1591784 for gift_card_1591784, all of a phone number."""
    if fact.kind == "identifier":
        m = re.search(r"[0-9]+$", fact.value)
        return m.group() if m else None
    return _digits(fact)


_SUFFIX_DIGITS = 4
"""Digits a last-digit reference needs to match the end of a long bare number (not an ID or phone)."""
_ACCOUNT_DIGITS = 7
"""Digits a bare quantity needs before it can be an account number whose end a reference names."""


def _ends_with(evidence: Fact, suffix: str) -> bool:
    """"Ending in 1784": an ID or phone ending so, or a number that is those digits or a long account
    number ending in them. Never a price or a count that happens to end in them ("1500", "12024")."""
    digits = _trailing_digits(evidence)
    if digits is None or not digits.endswith(suffix):
        return False
    if evidence.kind in ("identifier", "phone") or digits == suffix:
        return True
    return len(digits) >= _ACCOUNT_DIGITS and len(suffix) >= _SUFFIX_DIGITS


def _plain(evidence: Fact, amount) -> bool:
    """Evidence that states ``amount`` as a bare number: a quantity, or an all-digit ID ("2500000000").
    A segment of a mixed ID (credit_card_7574394) is a stated number but never an amount."""
    if evidence.kind == "quantity":
        return evidence.value == amount
    return evidence.kind == "identifier" and evidence.value.isdigit() and amount in evidence.numbers


def _url_matches(claim: str, evidence: str) -> bool:
    """The same page, or a less specific prefix of it (a domain supported by a deep link)."""
    return evidence == claim or (evidence.startswith(claim) and evidence[len(claim)] in "/?#")


def supports(evidence: Fact, claim: Fact) -> bool:
    kind = claim.kind
    if kind == "phone" or (evidence.kind == "phone" and kind in ("identifier", "quantity")):
        # "+60123456789", wa_id "60123456789" and {"phone": 60123456789} are one number
        a, b = _digits(claim), _digits(evidence)
        if a and b and _phone_matches(a, b):
            return True
        if kind == "phone":
            return False
    if kind == "quantity":
        return claim.value in evidence.numbers
    if kind == "money":
        currency, amount = claim.value
        if evidence.kind == "money":
            return evidence.value[1] == amount and _same_currency(currency, evidence.value[0])
        return _plain(evidence, amount)
    if kind == "percent":
        return (evidence.kind == "percent" and evidence.value == claim.value) or _plain(evidence, claim.value)
    if kind == "temperature":
        if evidence.kind == "temperature":
            return evidence.value == claim.value  # a conversion is a derived value (ADR-0005)
        return _plain(evidence, claim.value[0])
    if kind == "date":
        return evidence.kind == "date" and any(
            _date_matches(c, e) for c in claim.value for e in evidence.value)
    if kind == "identifier" and claim.value.startswith("*"):
        return _ends_with(evidence, claim.value[1:])
    if kind == "identifier" and claim.value.isdigit():
        if evidence.kind == "identifier":
            return evidence.value == claim.value  # codes are strings: "00123" is not "123"
        if evidence.kind == "url":
            return claim.value in _path_numbers(evidence.value)  # ".../pull/3337" states PR #3337, not 3337 lines
        return Decimal(claim.value) in evidence.numbers  # "#48213" and 48213, "1500000000" and "$1.5 billion"
    if kind == "identifier" and evidence.kind == kind and _GIT_HASH.fullmatch(claim.text) and _is_long_hash(evidence.text):
        return evidence.value.startswith(claim.value)  # "33e41b9" from 33e41b9670c2…; never longer than the Source
    if kind in ("identifier", "email"):
        return evidence.kind == kind and evidence.value == claim.value
    if kind == "url":
        if evidence.kind == "email":
            return _url_matches(claim.value, evidence.value.rsplit("@", 1)[1])
        return evidence.kind == "url" and _url_matches(claim.value, evidence.value)
    if kind == "time":
        return evidence.kind == "time" and not set(claim.value).isdisjoint(evidence.value)
    return False


# ---------------------------------------------------------------------------- the index
# check() visits, for each Claim, only the Evidence that shares a key with it. The keys are derived
# from supports() rule by rule, so supports(e, c) implies claim_keys(c) & evidence_keys(e): the
# index can only skip pairs supports() would reject. bench/index_differential.py checks this
# against the brute-force pairing.


def _phone_key(digits: str | None) -> tuple | None:
    """_phone_matches needs at least 7 digits after leading zeros, and equal last 7."""
    stripped = (digits or "").lstrip("0")
    return ("p", stripped[-7:]) if len(stripped) >= 7 else None


def evidence_keys(e: Fact) -> set[tuple]:
    keys: set[tuple] = {("n", x) for x in e.numbers}
    if e.kind in ("quantity", "percent"):
        keys.add(("n", e.value))
    elif e.kind == "money":
        keys.add(("n", e.value[1]))
    elif e.kind == "temperature":
        keys.add(("n", e.value[0]))
    elif e.kind == "date":
        keys |= {k for r in e.value for k in _date_keys(r)}
    elif e.kind == "time":
        keys |= {("t", r) for r in e.value}
    elif e.kind == "email":
        keys |= {("i", e.value), ("h", e.value.rsplit("@", 1)[1])}
    elif e.kind == "url":
        keys.add(("h", _host(e.value)))
        keys |= {("u", n) for n in _path_numbers(e.value)}
    elif e.kind == "identifier":
        keys.add(("i", e.value))
        if _is_long_hash(e.text):
            keys.add(("g", e.value[:7]))
    phone = _phone_key(_digits(e))
    if phone:
        keys.add(phone)
    trailing = _trailing_digits(e)
    if trailing and len(trailing) >= 3:  # _ends_with: an ID or phone ending so, or a long account number
        if e.kind in ("identifier", "phone") or len(trailing) >= _ACCOUNT_DIGITS:
            keys.add(("s", trailing[-3:]))
        keys.add(("sx", trailing))  # or the very digits ("last4": "4242")
    return keys


def claim_keys(c: Fact) -> set[tuple]:
    kind = c.kind
    keys: set[tuple] = set()
    if kind in ("quantity", "percent"):
        keys.add(("n", c.value))
    elif kind == "money":
        keys.add(("n", c.value[1]))
    elif kind == "temperature":
        keys.add(("n", c.value[0]))
    elif kind == "date":
        keys |= {_date_claim_key(r) for r in c.value}
    elif kind == "time":
        keys |= {("t", r) for r in c.value}
    elif kind == "email":
        keys.add(("i", c.value))
    elif kind == "url":
        keys.add(("h", _host(c.value)))
    elif kind == "identifier":
        if c.value.startswith("*"):
            keys |= {("s", c.value[-3:]), ("sx", c.value[1:])}
        elif c.value.isdigit():
            keys |= {("i", c.value), ("n", Decimal(c.value)), ("u", c.value)}
        else:
            keys.add(("i", c.value))
            if _GIT_HASH.fullmatch(c.text):
                keys.add(("g", c.value[:7]))
    if kind in ("phone", "identifier", "quantity"):
        phone = _phone_key(_digits(c))
        if phone:
            keys.add(phone)
    return keys


def _date_keys(reading: str) -> set[tuple]:
    """Every generalisation of an Evidence date: a Claim may state less than it (Specificity)."""
    year, month, day = reading[:4], reading[5:7], reading[8:]
    keys = {("m", month)}
    if day != "XX":
        keys.add(("md", month, day))
    if year != "XXXX":
        keys.add(("ym", year, month))
    if day != "XX" and year != "XXXX":
        keys.add(("ymd", year, month, day))
    return keys


def _date_claim_key(reading: str) -> tuple:
    """The most specific key a Claim date allows: Evidence that supports it states at least as much."""
    year, month, day = reading[:4], reading[5:7], reading[8:]
    if year != "XXXX" and day != "XX":
        return ("ymd", year, month, day)
    if day != "XX":
        return ("md", month, day)
    if year != "XXXX":
        return ("ym", year, month)
    return ("m", month)


def _host(url: str) -> str:
    return re.split(r"[/?#]", url, maxsplit=1)[0]
