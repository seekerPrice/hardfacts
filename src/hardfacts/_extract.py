"""Find Hard facts in text and read their Values.

Recognisers run in priority order. Each one claims the characters it matches, so a
later, looser recogniser can never re-read part of an earlier match (``21:0`` is a
time and never also the quantities 21 and 0).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import Context, Decimal
from typing import Any, Callable, Iterator


@dataclass(frozen=True)
class Fact:
    kind: str
    start: int
    end: int
    text: str
    value: Any
    numbers: frozenset[Decimal] = frozenset()
    """Plain numbers this Fact vouches for when it is Evidence for a bare quantity."""
    as_24_hour: tuple[str, ...] | None = None
    """For a time written without AM/PM ("9:00"): its Value if the text is on the 24-hour clock."""


def _compile(pattern: str, flags: int = 0) -> re.Pattern:
    """ASCII word semantics: 退款1200元 has a word boundary on both sides of 1200."""
    return re.compile(pattern, flags | re.ASCII)


Words = tuple[tuple[int, str], ...]
"""Every ASCII word in a text with its offset, lower-cased; computed once per extract()."""
Recogniser = Callable[[str, Words], Iterator[Fact]]

# --------------------------------------------------------------------------- numbers

NUM = r"(?<![\d,.])\d{1,3}\.\d{3},\d{1,2}(?!\d|[.,]\d|\])|\d{1,3}(?:\.\d{3}){2,}(?:,\d{1,2})?(?!\d|\.\d)|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+"
"""A number: European 1.500,00, dot-thousands with 2+ groups (1.500.000), comma-thousands (1,500,000), plain, or .5."""
MAGNITUDE_WORDS = {"thousand": 10**3, "lakh": 10**5, "lakhs": 10**5, "million": 10**6, "crore": 10**7,
                   "crores": 10**7, "billion": 10**9, "trillion": 10**12}
MALAY_MAGNITUDES = {"ribu": 10**3, "juta": 10**6, "bilion": 10**9, "miliar": 10**9, "trilion": 10**12, "triliun": 10**12}
MONEY_SUFFIXES = {"k": 10**3, "m": 10**6, "mn": 10**6, "mil": 10**6, "b": 10**9, "bn": 10**9, "t": 10**12, "tn": 10**12}
_MAGNITUDE_WORD = r"(?i:thousand|lakhs?|million|crores?|billion|trillion|ribu|juta|bilion|miliar|trilion|triliun)"


def _alternation(tokens) -> str:
    return "|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True))


_WORD_TOKEN = _compile(r"[A-Za-z]+")


def _words(text: str) -> Words:
    return tuple((m.start(), m.group().lower()) for m in _WORD_TOKEN.finditer(text))


def _anchored(pattern: re.Pattern, text: str, words: Words, keywords) -> Iterator[re.Match]:
    """``pattern.finditer`` for patterns that start with a keyword, tried only at those words.

    Scanning a long Source with a big case-insensitive alternation costs far more than
    tokenising once and matching at the handful of positions that could start a hit.
    """
    end = -1
    for pos, word in words:
        if pos < end or word not in keywords:
            continue
        if pos and (text[pos - 1].isalnum() or text[pos - 1] == "_"):
            continue
        m = pattern.match(text, pos)
        if m:
            end = m.end()
            yield m


EXACT = Context(prec=1000)
"""Arithmetic on Values never rounds: the default 28-digit context would round a 34-digit tracking number."""


_FLOAT_NOISE = _compile(r"(\d+)\.(\d*?)(0{6,}|9{6,})\d{0,3}")
"""Binary floating-point noise in a tool result: 302.67 - 298.91 prints as 3.759999999999991."""
_FLOAT_NOISE_DIGITS = 15
_LONGEST_FLOAT = 40
"""Characters a rendered double can take (17 digits and up to ~22 leading zeros); longer is no float,
and the lazy noise pattern is quadratic on a 40,000-digit number."""
"""A double holds 15-17 significant digits, so noise lives there: "5.1000000000009" (14) is a real value."""


_EUROPEAN = re.compile(r"\d{1,3}\.\d{3},\d{1,2}")


def to_decimal(digits: str) -> Decimal:
    if digits.count(".") >= 2 or _EUROPEAN.fullmatch(digits):  # "1.500.000", "1.500,00": dots group thousands, a comma marks decimals
        return Decimal(digits.replace(".", "").replace(",", "."))
    digits = digits.replace(",", "")
    noise = len(digits) <= _LONGEST_FLOAT and _FLOAT_NOISE.fullmatch(digits)
    if noise and len(digits.replace(".", "").lstrip("0")) >= _FLOAT_NOISE_DIGITS:  # "3.759999999999991" is 3.76
        whole, kept, run = noise.group(1, 2, 3)
        value = Decimal(f"{whole}.{kept}" if kept else whole)
        return EXACT.add(value, Decimal(1).scaleb(-len(kept))) if run[0] == "9" else value
    return Decimal(digits)


def scale(number: str, magnitude: str | None) -> tuple[Decimal, frozenset[Decimal]]:
    """The Value of a number with an optional magnitude, and every number it vouches for."""
    base = to_decimal(number)
    if not magnitude:
        return base, frozenset({base})
    word = magnitude.lower()
    factor = MAGNITUDE_WORDS.get(word) or MALAY_MAGNITUDES.get(word) or MONEY_SUFFIXES[word]
    value = EXACT.multiply(base, Decimal(factor))
    return value, frozenset({value, base})


# ----------------------------------------------------------------------- exempt spans

_LIST_MARKER = _compile(r"(?m)^[ \t]*(?:[-*•][ \t]*)?(?:step[ \t]+)?\d{1,3}(?:[.):]|[ \t]*[-–—:])(?=[ \t]|$)", re.I)
_OUTPUT_LENGTH = _compile(
    r"\b(?:in|within|under|of|to|about|around|approximately|exactly|less than|fewer than|at most|no more than)"
    r"[ \t]+(?:about[ \t]+|around[ \t]+|approximately[ \t]+|exactly[ \t]+)?(\d{1,4})[ \t]+"
    r"(?:words?|sentences?|paragraphs?|bullet points?)\b",
    re.I,
)


_N_WORD = _compile(r"\b\d{1,4}-(?:words?|sentences?|paragraphs?)\b", re.I)
_EVERY_DAY = _compile(
    r"\b(?:seven|7)\s+days\s+a\s+week\b|\b24\s*/\s*7\b|\b24\s+hours\s+a\s+day\b|\b365\s+days\s+a\s+year\b", re.I
)


_HTML_ENTITY = _compile(r"&#?\w{1,8};")
_RATING_SCALE = _compile(r"\bout\s+of\s+((?:5|10|100)(?:\.0)?)\b(?![.,]?\d)", re.I)


_SELF_REFERENCE = _compile(
    r"\b(?:steps?|passages?|reviews?|facts?|points?|tips?|methods?|options?)\s+"
    r"(\d{1,3}(?:\s*(?:,|and|or|&|-|–|to)\s*\d{1,3})*)\b",
    re.I,
)
"""The Output pointing at its own structure or the prompt's: "repeat steps 6 and 7", "(Passage 2)"."""


_CITATION = _compile(
    r"\[(\^|(?:doc(?:ument)?|source|ref)\s*)?\d{1,2}(?:\s*[,–-]\s*\^?\d{1,2}){0,5}\]", re.I)
"""A citation marker's shape: "[10]", "[1, 2, 5]", "[1-6]", "[^2]", "[Doc 3]", with at most six entries
of up to two digits each, so "[101, 102]" and "[2024]" are always values."""
_CLOSES_A_CLAUSE = _compile(r"\s*(?:$|[.,;:!?)\[\n]|\s[A-Z])")
_INTRODUCES_A_VALUE = {
    "is", "are", "was", "were", "be", "been", "equals", "equal", "at", "to", "of", "in", "from", "between",
    "about", "around", "approximately", "only", "aged", "age", "ages", "seat", "seats", "answer", "coordinates",
    "values", "scores", "numbers", "ids", "list", "array", "vector", "range", "interval", "set", "takes", "take",
}


def _citations(text: str, words: Words) -> Iterator[Fact]:
    """Citation markers close a clause: "were killed [10].", "the dominant language [2, 3, 5, 6] It".

    A bracket that a value-introducing word leads into ("the scores were [7, 8, 9]", "seat [12] is") or
    that sits in code or a list (":", "=", "{") is a value. "[^2]" and "[Doc 3]" are always citations."""
    for m in _CITATION.finditer(text):
        if not m.group(1):
            before = text[max(0, m.start() - 40):m.start()].rstrip(" \t\n\r\f\v")
            last = re.search(r"([A-Za-z]+)$", before)
            if (not before or before[-1] in ":={(,[" or (last and last.group(1).lower() in _INTRODUCES_A_VALUE)
                    or not _CLOSES_A_CLAUSE.match(text, m.end())):
                continue
        yield Fact(EXEMPT, m.start(), m.end(), m.group(), None)


EXEMPT = "exempt"
"""Marks an Exempt span while recognisers run. It claims its characters, then is dropped: never a Claim."""
_EXEMPTIONS = [  # (pattern, group whose span is exempt)
    (_SELF_REFERENCE, 1), (_RATING_SCALE, 1), (_HTML_ENTITY, 0), (_EVERY_DAY, 0), (_LIST_MARKER, 0),
    (_OUTPUT_LENGTH, 1), (_N_WORD, 0),
]


def _exempt(text: str, words: Words) -> Iterator[Fact]:
    """Spans that look like Hard facts but assert nothing about the world."""
    for pattern, group in _EXEMPTIONS:
        for m in pattern.finditer(text):
            yield Fact(EXEMPT, m.start(group), m.end(group), m.group(group), None)
    yield from _citations(text, words)


# ------------------------------------------------------------ contacts and identifiers

_URL_CHAR = (r"[^\s<>\"'()\[\]{}\u2018\u2019\u201c\u201d]"
             r"|[\u2018\u2019\u201c\u201d](?=[^\s<>\"'()\[\]{}\u2018\u2019\u201c\u201d.,;:!?*`])")
"""A URL character; a curly quote only inside a word ("/o’neill-jacket"), so “…/wapenc.” ends at the stop."""
_URL = _compile(
    rf"(?:https?://|www\.)(?:{_URL_CHAR})+"
    rf"|(?<![\w.-])[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/(?:{_URL_CHAR})*)?",
    re.I,
)
"""A scheme URL, or a bare dotted host (checked for a known TLD after matching, which keeps the
pattern linear: a TLD alternation inside the repetition backtracks quadratically on "a.a.a…").
"""
_TLDS = {"com", "org", "net", "io", "ai", "gov", "edu", "co", "my", "sg", "uk", "app", "dev", "info", "biz"}
_EMAIL = _compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = _compile(
    r"(?<![\w+.,/-])(\+\d{1,3}[ .-]?)?(\(\d{1,4}\)[ .-]?)?(\d{1,4})((?:[ .-]\d{2,8}){1,4})(?![\w.,/-]?\d)"
)
_PHONE_PLAIN = _compile(r"(?<![\w+.,/-])(?:\+\d{8,15}|0\d{8,10})(?![\w.,/-]?\d)")
"""Unformatted numbers as CRMs store them: "+60123456789", "0123456789"."""
_PHONE_CUE = _compile(
    r"(?:\b(?:call|calls|phone|tel|telephone|hotline|whatsapp|mobile|fax|contact|sms|text|hubungi|telefon|nombor)\b"
    r"|电话|手机|联系|致电|拨打|热线|号码)[^\d\n]{0,15}\Z",
    re.I,
)
_IDENTIFIER = _compile(r"(?<![\w#@/.-])#?(?=[A-Za-z0-9_/-]*\d)[A-Za-z0-9]+(?:[-_/][A-Za-z0-9]+)*(?![\w@])")
_NOT_IDENTIFIER = _compile(
    r"\d+(?:\.\d+)?(?:st|nd|rd|th|s|x|k|kg|g|mg|lb|lbs|oz|km|m|cm|mm|mi|ft|in|mph|kph|kmh|hr|hrs|h|min|mins|"
    r"sec|secs|ms|am|pm|gb|mb|kb|tb|ghz|mhz|hz|w|kw|kwh|v|ml|l|cc|mp|p|fps|bn|mn|b|yr|yrs|d|wk|wks|D|"
    r"psi|rpm|kcal|cal|mah|db|ppm|mbps|gbps|kbps|lm|nm|mcg|iu|gal|qt|pt|tbsp|tsp|ha|sqft|ah|mw|gw)",
    re.I,
)


_BOOKING_CODE = _compile(r"[A-Z0-9]{6}")
"""An airline record locator ("XEHM8B"): six capitals and digits, often with a single digit."""
_BOOKING_CUE = _compile(
    r"\b(?:bookings?|reservations?|confirmations?|pnr|locator|ref|flights?|trips?|itinerar(?:y|ies)|tempahan)(?![a-z])"
    r"[^\n]{0,50}\Z", re.I)
_NAME_SHAPED = _compile(r"[A-Z]{4,5}[0-9]{1,2}")


def _is_booking_code(text: str, start: int, surface: str) -> bool:
    """"XEHM8B" and "FDZ4T5" are codes; "LLAMA3", "BASE64" and "SAVE20" are names: letters, then a
    version or amount. A name-shaped code is a code only after a booking word ("flight XEHM82")."""
    if not _BOOKING_CODE.fullmatch(surface):
        return False
    return not _NAME_SHAPED.fullmatch(surface) or bool(_BOOKING_CUE.search(text[max(0, start - 60):start]))


_STATED_SEGMENT = 6
"""Digits an ID's segment needs before it counts as a stated number: account numbers, not ORD-2500."""


def _strip_trailing_punctuation(m: re.Match) -> tuple[int, int, str]:
    text = m.group().rstrip(".,;:!?")
    return m.start(), m.start() + len(text), text


def normalise_url(url: str) -> str:
    url = re.sub(r"^(?:https?://)?(?:www\.)?", "", url.lower())
    return url.rstrip("/")


_URL_HINTS = ("http", "www.", ".com", ".org", ".net", ".io", ".ai", ".gov", ".edu", ".co", ".my", ".sg", ".uk",
              ".app", ".dev", ".info", ".biz")


def _urls(text: str, words: Words) -> Iterator[Fact]:
    lowered = text.lower()
    if not any(hint in lowered for hint in _URL_HINTS):
        return
    for m in _URL.finditer(text):
        surface = m.group().rstrip(".,;:!?*`")  # Markdown too: "**https://…/637**", "`app.vercel.app/tree`"
        start, end = m.start(), m.start() + len(surface)
        if not re.match(r"(?:https?://|www\.)", surface, re.I):
            host = surface.split("/", 1)[0]
            known = _known_host(host.split("."))
            if known is None:
                continue
            if known != host:  # "HP.com.Click Support": a sentence joined on without a space
                surface = known
                end = start + len(known)
        yield Fact("url", start, end, surface, normalise_url(surface))


_SECOND_LEVEL = {"com", "co", "org", "net", "gov", "edu", "ac"}


def _known_host(labels: list[str]) -> str | None:
    """The host a bare dotted name names, or None when its last label is no TLD ("report.pdf")."""
    last = labels[-1].lower()
    if last in _TLDS or (len(labels) >= 3 and len(last) == 2 and last.isalpha() and labels[-2].lower() in _SECOND_LEVEL):
        return ".".join(labels)  # "example.com", "example.com.au", "foo.co.jp"
    for k in range(len(labels) - 2, 0, -1):
        if labels[k].lower() in _TLDS and labels[k + 1][:1].isupper():
            return ".".join(labels[:k + 1])
    return None


def _emails(text: str, words: Words) -> Iterator[Fact]:
    if "@" not in text:
        return
    for m in _EMAIL.finditer(text):
        start, end, surface = _strip_trailing_punctuation(m)
        yield Fact("email", start, end, surface, surface.lower())


def _cued(text: str, start: int) -> bool:
    return bool(_PHONE_CUE.search(text[max(0, start - 30):start]))


def _phones(text: str, words: Words) -> Iterator[Fact]:
    """Phone numbers. Dots and spaces also group thousands ("Rp 1.500.000", "1 234 567") and
    separate table columns, so a number grouped only by them needs a country code, a trunk 0,
    the North American 3-3-4 shape, or a cue word ("call", "hotline") before it to count as a phone."""
    for m in _PHONE.finditer(text):
        if _AFTER_CURRENCY.search(text[max(0, m.start() - 8):m.start()]):
            continue  # "$1.500.000" is money, even after "call now for"
        country, area, first, rest = m.groups()
        digits = re.sub(r"\D", "", m.group())
        groups = [g for g in re.split(r"[ .-]+", rest.strip(" .-")) if g]
        lengths = [len(first), *map(len, groups)]
        marked = bool(country or area)
        trunk = first.startswith("0") and 9 <= len(digits) <= 11
        nanp = lengths in ([3, 3, 4], [1, 3, 3, 4])  # 212.555.0199, 1 800 555 0199
        thousands = len(first) <= 3 and all(n == 3 for n in lengths[1:])
        if "-" in rest:
            shaped = len(groups) >= 2 or (len(groups) == 1 and (
                (first.startswith("0") and 6 <= len(groups[0]) <= 8) or (len(first) == 3 and len(groups[0]) == 4)))
            ok = marked or shaped
        else:
            ok = marked or trunk or nanp or (not thousands and _cued(text, m.start()))
        if 7 <= len(digits) <= 15 and ok:
            yield Fact("phone", m.start(), m.end(), m.group(), digits)
    for m in _PHONE_PLAIN.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if m.group().startswith("+") and not _cued(text, m.start()) and (
                len(digits) < 10 or _BEFORE_WORD.match(text, m.end())):
            continue  # "+12500000 this month" is a change in a count
        yield Fact("phone", m.start(), m.end(), m.group(), digits)


_BEFORE_WORD = _compile(r"\s+[a-z]")


_ELLIPSIS = r"(?:\*+|…|\.{3})?"
"""What may stand for the hidden digits before the last ones: "ending in **1784", "…1863", "...1863"."""
_ENDING = _compile(rf"\b(ending|ends)(?:\s+(?:in|with))?(?:\s*:)?\s*{_ELLIPSIS}(\d{{3,6}})(?!\d|[.,]\d)", re.I)
_ACCOUNT_CUE = _compile(
    r"\b(?:card|account|acct|number|no|phone|mobile|line|sim|id|visa|mastercard|amex|debit|credit|certificate|voucher|paypal|"
    r"kad|akaun|telefon)\b[^\n]{0,30}\Z", re.I)
_TIME_NOUN = _compile(
    r"\b(?:years?|plan|contract|subscription|term|lease|period|season|promo(?:tion)?|offer|warranty|trial|"
    r"membership|quarter|month)\b", re.I)
_YEAR_LIKE = _compile(r"(?:19|20)\d\d")
_LINE_CUE = _compile(r"\b(?:line|sim)\b[^\n]{0,30}\Z", re.I)
"""A phone line that "ends in 2025" ends in that year; a line "ending in 2025" is named by its digits."""
_CARD_WORD = _compile(r"\b(?:card|visa|mastercard|amex|debit|credit|kad)\b", re.I)


def _time_is_nearer(window: str) -> bool:
    """A time noun closer to "ends in" than any card word: "card's promotional period ends in 2025"."""
    times = [m.start() for m in _TIME_NOUN.finditer(window)]
    cards = [m.start() for m in _CARD_WORD.finditer(window)]
    return bool(times) and (not cards or times[-1] > cards[-1])
_LAST_N_DIGITS = _compile(
    r"\blast\s+(?:3|4|5|6|three|four|five|six)\s+(?:digits|numbers)(?:\s+of(?:\s+[a-z]+){1,4}?)?"
    rf"(?:\s*(?::|\bis\b|\bare\b))?\s*{_ELLIPSIS}(\d{{3,6}})(?!\d|[.,]\d)", re.I)
"""Each run of spaces has one owner, so a failed match backtracks linearly (not "of" + 20,000 spaces)."""
_MASK_RUN = _compile(r"[*xX•·](?:[*xX•· -]*[*xX•·])?")
"""A maximal run of mask characters, found left to right without rescanning: linear on 50 KB of "*"."""
_AFTER_MASK = _compile(r"[ -]?(\d{3,6})(?!\d|[.,]\d)")
_SMALLEST_MASK = 3
"""Mask characters a card mask needs ("****", "xxxx", "•••"); two do when the digits touch ("••4242", "xx-4242")."""


def _is_mask(marks: list[str], gap: str, after: str) -> bool:
    """"**500**" is Markdown bold and "•• 1200" a separator, not masks; "**** 4242" and "Visa ••4242" are."""
    if set(marks) == {"*"}:
        return len(marks) >= _SMALLEST_MASK and after != "*"
    return len(marks) >= _SMALLEST_MASK or (len(marks) == 2 and gap in ("", "-"))


def _last_digits(text: str, words: Words) -> Iterator[Fact]:
    """"The card ending in 1784", "last four digits are 5678", "**** 4242": the end of a longer number.

    The Value is the digits after a "*" (``*1784``), a less specific statement of any number that
    ends with them, as ``February 7`` is of ``February 7, 1945``. "Ending in" needs an account word
    before it, and a year after it is a year when a time word is near ("the plan ends in 2025")."""
    for m in _ENDING.finditer(text):
        window = text[max(0, m.start() - 40):m.start()]
        if not _ACCOUNT_CUE.search(window):
            continue
        if _YEAR_LIKE.fullmatch(m.group(2)) and (_time_is_nearer(window) or (
                m.group(1).lower() == "ends" and _LINE_CUE.search(window) and not _CARD_WORD.search(window)
                and text[m.start(2) - 1] not in "*….")):
            continue  # "the trial on your account ends in 2025", "your line ends in 2025"; but "your Visa card ends in 2024" is a card
        yield Fact("identifier", m.start(2), m.end(2), m.group(2), "*" + m.group(2))
    for m in _LAST_N_DIGITS.finditer(text):
        yield Fact("identifier", m.start(1), m.end(1), m.group(1), "*" + m.group(1))
    if not any(ch in text for ch in "*xX•·"):
        return
    for run in _MASK_RUN.finditer(text):
        before = text[run.start() - 1] if run.start() else ""
        if before.isascii() and before.isalnum():
            continue
        m = _AFTER_MASK.match(text, run.end())
        marks = [ch for ch in run.group() if ch not in " -"]
        if not m or not _is_mask(marks, text[run.end():m.start(1)], text[m.end(1):m.end(1) + 1]):
            continue
        yield Fact("identifier", m.start(1), m.end(1), m.group(1), "*" + m.group(1))


_NUMBER_COMPOUND = _compile(
    r"\d+(?:\.\d+)?s?(?:-(?:[a-z]+|\d+(?:\.\d+)?))+"
    r"|[a-z]+-\d+(?:\.\d+)?s?"
    r"|\d+(?:\.\d+)?(?:[x×]\d+(?:\.\d+)?)+"
)
""""73-year-old", "6-to-12", "mid-1800s", "magnitude-7.8", "8x10": the numbers are quantities."""


_LIST_ITEM = _compile(r"[A-Za-z]{1,3}")
"""A short word in a slash list: "etc", "LTE". A name with a digit ("i5", "M2") keeps the run a code."""


def _is_slash_list(surface: str) -> bool:
    """"5G/4G/3G/2G" and "100Mbps/20Mbps" list alternatives or specs; each part is read on its own.

    Every part is a measure ("5G", "32GB") or a short word ("etc", "LTE"), and at least one is a
    measure, so codes keep their slashes: "INV/2024/0012", "12A/12B", "A1/B2/C3", "i7/16GB/1TB"."""
    parts = surface.split("/")
    if len(parts) < 2 or any(not p for p in parts):
        return False
    measures = [bool(_NOT_IDENTIFIER.fullmatch(p)) for p in parts]
    return any(measures) and all(m or _LIST_ITEM.fullmatch(p) for m, p in zip(measures, parts))


def _source_identifiers(text: str, words: Words) -> Iterator[Fact]:
    return _identifiers(text, words, in_source=True)


def _identifiers(text: str, words: Words, in_source: bool = False) -> Iterator[Fact]:
    """Codes mixing letters and digits: tracking numbers, order IDs, SKUs.

    Short mixes ("COVID-19", "B12", "7-Eleven") are names, not codes. They are claimed
    as Exempt spans so their digits are never re-read as quantities.
    """
    for m in _IDENTIFIER.finditer(text):
        start, end, surface = _strip_trailing_punctuation(m)
        core = re.sub(r"[^A-Za-z0-9]", "", surface)
        digits = sum(ch.isdigit() for ch in core)
        letters = len(core) - digits
        if not letters and digits >= 10 and not re.match(r"[.,][0-9]", text[end:end + 2]):
            # FedEx, USPS, Amazon: long all-digit codes are IDs, not amounts (a decimal point says amount)
            yield Fact("identifier", start, end, surface, core, frozenset({Decimal(core)}))
            continue
        if _NUMBER_COMPOUND.fullmatch(surface) or _is_slash_list(surface):
            continue
        is_number_tag = surface.startswith("#") and core.isdigit() and digits >= 3
        if not (letters and digits or is_number_tag) or _NOT_IDENTIFIER.fullmatch(core):
            continue
        if is_number_tag:  # "#48213" is the number 48213 with a tag
            yield Fact("identifier", start, end, surface, core, frozenset({Decimal(core)}))
        elif digits >= 4 or (digits >= 3 and letters >= 2) or (
                _BOOKING_CODE.fullmatch(surface) if in_source else _is_booking_code(text, start, surface)):
            # "credit_card_7574394" states the number 7574394; short segments ("ORD-2500") are labels
            segments = frozenset(Decimal(p) for p in re.split(r"[-_/]", surface.lstrip("#"))
                                 if p.isdigit() and len(p) >= _STATED_SEGMENT and p[0] != "0")
            yield Fact("identifier", start, end, surface, core.upper(), segments)
        else:
            yield Fact(EXEMPT, start, end, surface, None)


# ------------------------------------------------------------------------------ date

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4,
    "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9,
    "sept": 9, "sep": 9, "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
    # Bahasa Melayu / Indonesia
    "januari": 1, "februari": 2, "mac": 3, "maret": 3, "mei": 5, "juni": 6, "julai": 7, "juli": 7,
    "ogos": 8, "agustus": 8, "oktober": 10, "okt": 10, "disember": 12, "desember": 12, "dis": 12,
}
_MONTH_NAMES = [m for m in _MONTHS if (len(m) > 3 or m in ("may", "mac", "mei")) and m != "sept"]
_MONTH_ABBREVIATIONS = [m for m in _MONTHS if m not in _MONTH_NAMES]
_MONTH = rf"({_alternation(_MONTH_NAMES)}|(?:{_alternation(_MONTH_ABBREVIATIONS)})(?![a-z])\.?)"
_DAY = r"(\d{1,2})(?!\d)(?:st|nd|rd|th|hb)?"  # "hb": Malay haribulan, "3hb Oktober"
_YEAR = r"(\d{4})"
_ISO_DATE = _compile(r"(?<![\w.])(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?![\d])")
_COMMA = r"(?:\s?,\s*|\s+)"  # "July 22, 1947", tokenised text's "July 22 , 1947", and a contract's "October 1,1996"
_YEAR2 = r"'?(\d{2})(?![.:]\d)(?=\s*(?:[.,;:)!?]|$))(?!\s*,?\s*\d{4})"
"""A two-digit year only where a sentence could end ("3 Oct 26."), and never before a full year ("Oct 26, 2025")."""
_MONTH_FIRST = _compile(rf"{_MONTH}(?:\s+{_DAY}(?!\s?%)(?:{_COMMA}{_YEAR})?|{_COMMA}{_YEAR})(?!\w|:\d)", re.I)
_DAY_FIRST = _compile(rf"(?<![\w.]){_DAY}[ \t](?:day\s+of\s+|of\s+)?{_MONTH}(?:{_COMMA}{_YEAR}|[ \t]+{_YEAR2})?(?!\w|:\d)", re.I)
""""3 October 2026", "3 Oct 26": the day and month on one line, one space apart (a table's
"3  Oct 26, 2025" is a count and a date); a two-digit year never after a comma ("3 March, 45")."""
_DAY_FIRST_RANGE = _compile(rf"(?<![\w.]){_DAY}(?:\s?[-–]\s?|\s+(?:and|&|to)\s+){_DAY}[ \t](?:of\s+)?{_MONTH}(?:{_COMMA}{_YEAR})?(?!\w|:\d)", re.I)
_HYPHEN_DATE = _compile(rf"(?<![\w.-])(\d{{1,2}})-{_MONTH}-(\d{{4}}|\d{{2}})(?![\w-])", re.I)
_NOT_A_DAY = r"(?!\s+(?:place|grade|graders?|years?|floors?|rounds?|century|time|anniversary)\b)"
"""After the second day of "May 2nd and 3rd place": a rank, not a date."""
_DAY_RANGE = _compile(
    rf"{_MONTH}\s+{_DAY}(?:\s?[-–]\s?|\s+(?:and|&|to)\s+(?=\d{{1,2}}(?:st|nd|rd|th)|\d{{1,2}}{_COMMA}\d{{4}}(?!\d)))"
    rf"{_DAY}{_NOT_A_DAY}(?:{_COMMA}{_YEAR})?(?!\w|:\d)", re.I)
""""March 10-12, 2015", and "May 19th and 20th": in an Output a word joins two days only when the
second is ordinal or a year follows ("May 27 and 28, 2024"), so "May 5 and 6 people" keeps its count."""
_DAY_RANGE_IN_SOURCE = _compile(
    rf"{_MONTH}\s+{_DAY}(?:\s?[-–]\s?|\s+(?:and|&|to)\s+){_DAY}{_NOT_A_DAY}(?:{_COMMA}{_YEAR})?(?!\w|:\d)", re.I)
"""A Source reads "May 19 and 20" as two dates too (Evidence may be generous: ADR-0003). The second day
also vouches for its number, so an Output's "6 people" still finds the 6 in "May 5 and 6 people"."""
_NUMERIC_DATE = _compile(r"(?<![\w./])(\d{1,2})([/.])(\d{1,2})\2(\d{4})(?![\w/])")
_NUMERIC_MONTH_DAY = _compile(r"(?<![\w./])(\d{1,2})/(\d{1,2})(?![\w/]|[.,]\d|\s*%)")
""""on 5/19", "by 22/05": a date without a year only when one part is over 12, so the order can't be
misread; "1/2", "5/6" and "24/7" stay what they were."""
_DATE_WORD = _compile(
    r"(?:\b(?:on|by|until|till|due|before|after|from|since|through|thru|to|and|dated?|valid|effective|expires?|expiring|"
    r"departs?|departing|arrives?|arriving|returns?|returning|starts?|starting|ends?|ending|"
    r"deliver(?:y|s|ed)?|ship(?:s|ped|ping)?|dispatch(?:ed)?|eta|sampai)|[-–])\s*\Z", re.I)
"""A numeric month/day needs a date word before it: "on 5/19", "from 5/19 to 5/22". Without one,
"3/16 inch", "16/9" and "7/13 games" are fractions, and a Source's fraction must not vouch for a date.
A range to another date is date enough: "3/19 - 3/30/2017"."""
_STRONG_DATE_WORD = _compile(r"\b(?:on|dated?|due|expires?|expiring|departs?|departing|arrives?|arriving|returns?|returning|deliver(?:y|s|ed)?|ship(?:s|ped|ping)?|dispatch(?:ed)?|eta|sampai)\s*\Z", re.I)
"""Only these make "3/10" a date when either order could be one: "arrive 3/10", "on 10/3", "due 1/2"."""
_FRACTION_OF = _compile(r"\s*(?:of\b|cups?\b|inch(?:es)?\b|hours?\b|miles?\b|teaspoons?\b|tablespoons?\b)", re.I)
"""After "on 3/4" or "shipped 2/3": "of the days", "cup", "inch" make it a fraction."""
_TO_A_DATE = _compile(r"\s*(?:[-–]|to|through|thru|until)\s*\d{1,2}/\d{1,2}(?!\d)", re.I)


def _date_value(year, month, day) -> str | None:
    """EDTF-style "YYYY-MM-DD" with X for unstated parts, or None when out of range."""
    y = int(year) if year else None
    m = month if isinstance(month, int) else (int(month) if month and month.isdigit() else _MONTHS.get((month or "").lower().rstrip(".")))
    d = int(day) if day else None
    if (y is not None and not 1000 <= y <= 2999) or m is None or not 1 <= m <= 12 or (d is not None and not 1 <= d <= 31):
        return None
    return f"{y if y is not None else 'XXXX'}-{m:02d}-{d:02d}" if d else f"{y if y is not None else 'XXXX'}-{m:02d}-XX"


def _date_fact(text: str, start: int, end: int, readings: list[str | None], also: set[Decimal] = frozenset()) -> Fact | None:
    """A date Fact; it vouches for its years, and for ``also``."""
    readings = sorted({r for r in readings if r})
    if not readings:
        return None
    years = {Decimal(r[:4]) for r in readings if r[0] != "X"}
    return Fact("date", start, end, text[start:end], tuple(readings), frozenset(years | set(also)))


_ISO_DATETIME = _compile(
    r"(?<![\w.])(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?(?!\w)"
)
"""2026-10-03T14:00:00+08:00: a date, a 24-hour time, and a tail (seconds, offset) that is neither."""


def _iso_datetimes(text: str, words: Words) -> Iterator[Fact]:
    for m in _ISO_DATETIME.finditer(text):
        year, month, day, hour, minute = m.groups()
        date = _date_value(year, month, day)
        if date is None or int(hour) > 23 or int(minute) > 59:
            continue
        yield Fact("date", m.start(1), m.end(3), text[m.start(1):m.end(3)], (date,), frozenset({Decimal(year)}))
        yield Fact("time", m.start(4), m.end(5), text[m.start(4):m.end(5)], _clock_value({(int(hour), int(minute))}))
        if m.end(5) < m.end():
            yield Fact(EXEMPT, m.end(5), m.end(), text[m.end(5):m.end()], None)


_CJK_DATE = _compile(r"(?:(\d{4})\s?年\s?)?(\d{1,2})\s?月(?:\s?(\d{1,2})\s?[日号])?")


def _source_dates(text: str, words: Words) -> Iterator[Fact]:
    return _dates(text, words, in_source=True)


def _dates(text: str, words: Words, in_source: bool = False) -> Iterator[Fact]:
    found: list[tuple[int, int, list[str | None]]] = []
    if "月" in text:
        for m in _CJK_DATE.finditer(text):
            year, month, day = m.groups()
            if year or day:  # "3月" alone is a month name, not a date
                found.append((m.start(), m.end(), [_date_value(year, int(month), day)]))
    for m in _ISO_DATE.finditer(text):
        found.append((m.start(), m.end(), [_date_value(*m.groups())]))
    for m in _anchored(_DAY_RANGE_IN_SOURCE if in_source else _DAY_RANGE, text, words, _MONTHS):  # both ends are dates
        month, first, last, year = m.groups()
        found.append((m.start(), m.end(2), [_date_value(year, month, first)]))
        # in a Source, the second day of "May 5 and 6" also vouches for its number (a count may follow);
        # of "March 10-12" it doesn't
        worded = in_source and re.search(r"\band\b|&", text[m.end(2):m.start(3)], re.I) is not None  # not "10 to 12"
        found.append((m.start(3), m.end(), [_date_value(year, month, last)], {Decimal(last)} if worded else set()))
    for m in _anchored(_MONTH_FIRST, text, words, _MONTHS):
        month, day, year_after_day, year_alone = m.groups()
        if _is_apple_mac(text, month, m.end()):
            continue
        found.append((m.start(), m.end(), [_date_value(year_after_day or year_alone, month, day)]))
    for m in _DAY_FIRST_RANGE.finditer(text):  # "3–5 October 2026": both ends are dates
        first, last, month, year = m.groups()
        found.append((m.start(), m.end(1), [_date_value(year, month, first)]))
        found.append((m.start(2), m.end(), [_date_value(year, month, last)]))
    for m in _DAY_FIRST.finditer(text):
        day, month, year, year2 = m.groups()
        if _is_apple_mac(text, month, m.end()):
            continue
        found.append((m.start(), m.end(), [_date_value(year or _full_year(year2), month, day)]))
    for m in _HYPHEN_DATE.finditer(text):  # "3-Oct-2026", "03-OCT-26"
        day, month, year = m.groups()
        found.append((m.start(), m.end(), [_date_value(_full_year(year), month, day)]))
    for m in _NUMERIC_MONTH_DAY.finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        before = text[max(0, m.start() - 20):m.start()]
        if (a > 12 and b > 12) or not a or not b or not (_DATE_WORD.search(before) or _TO_A_DATE.match(text, m.end())):
            continue  # "13/20" is neither; "3/16 inch" has no date word
        if a <= 12 and b <= 12 and (not _STRONG_DATE_WORD.search(before) or _FRACTION_OF.match(text, m.end())):
            continue  # "after 1/2 hour", "and 1/4 cup": either order is a fraction first
        # "arrive 3/10" is 3 October in Malaysia and 10 March in the US: both readings, doubt is Supported
        readings = [(a, b)] if b > 12 else [(b, a)] if a > 12 else [(a, b), (b, a)]
        found.append((m.start(), m.end(), [_date_value(None, month, day) for month, day in readings],
                      {Decimal(a), Decimal(b)} if in_source else set()))
    for m in _NUMERIC_DATE.finditer(text):
        a, _, b, year = m.groups()
        found.append((m.start(), m.end(), [_date_value(year, int(b), a), _date_value(year, int(a), b)]))  # d/m or m/d
    facts = [f for f in (_date_fact(text, *found_) for found_ in found) if f]
    # Of two overlapping readings the one stating more is right ("3 Oct 26." is 3 October 2026, and
    # "3 Oct 26, 2025" is 26 October 2025 after a count); then the earliest, then the longest.
    facts.sort(key=lambda f: (-_stated_parts(f), f.start, f.start - f.end))
    yield from facts


def _stated_parts(fact: Fact) -> int:
    """How many of year, month and day the Fact's least specific reading states."""
    return min(sum(part[0] != "X" for part in reading.split("-")) for reading in fact.value)


def _full_year(year: str | None) -> str | None:
    """"26" → "2026", "85" → "1985": the POSIX pivot (69-99 are 19xx)."""
    if not year or len(year) == 4:
        return year
    return f"{19 if int(year) >= 69 else 20}{year}"


_APPLE_NOUN = _compile(r"\s+(?:laptops?|book|pro|mini|air|os|computers?|users?|apps?|address|store|studio)\b", re.I)


def _is_apple_mac(text: str, month: str, end: int) -> bool:
    """"5 Mac laptops" is a computer; "5 Mac" is Malay for 5 March."""
    return month.lower() == "mac" and bool(_APPLE_NOUN.match(text, end))


# ----------------------------------------------------------------------------- money

_PREFIX_CURRENCIES = {
    "US$": "USD", "S$": "SGD", "A$": "AUD", "C$": "CAD", "HK$": "HKD", "NZ$": "NZD", "$": "$",
    "€": "EUR", "£": "GBP", "¥": "¥", "₹": "INR", "₱": "PHP", "₫": "VND", "฿": "THB",
    "RM": "MYR", "Rp": "IDR", "Rs.": "INR", "Rs": "INR",
}
_CODES = ("USD", "SGD", "MYR", "EUR", "GBP", "JPY", "CNY", "RMB", "INR", "IDR", "THB", "PHP", "VND", "AUD", "CAD", "HKD", "NZD")
_SUFFIX_CURRENCIES = {
    "dollar": "$", "dollars": "$", "ringgit": "MYR", "euro": "EUR", "euros": "EUR", "yen": "JPY",
    "yuan": "CNY", "rupee": "INR", "rupees": "INR", "baht": "THB", "peso": "PHP", "pesos": "PHP",
    "rupiah": "IDR", "dong": "VND",
}
DOLLAR_FAMILY = {"$", "USD", "SGD", "AUD", "CAD", "HKD", "NZD"}
YEN_FAMILY = {"¥", "JPY", "CNY"}


_AFTER_CURRENCY = _compile(rf"(?:{_alternation(list(_PREFIX_CURRENCIES) + list(_CODES))})\s?\Z")


def _currency(token: str) -> str:
    code = _PREFIX_CURRENCIES.get(token) or _SUFFIX_CURRENCIES.get(token.lower()) or token.upper()
    return "CNY" if code == "RMB" else code


_MONEY_MAGNITUDE = (
    rf"(?:\s?({_MAGNITUDE_WORD})\b|\s?((?i:mil|bn|mn|tn))\b|((?i:[kmbt]))(?!\w|-(?!RM|Rp|Rs|[A-Z]{{1,2}}\$)[A-Za-z]))?"
)
"""A one-letter suffix must touch the number ("$3M"), so "RM20 T-shirt" is not 20 trillion; "$5K-$10K" is a range."""
_MONEY_BEFORE = _compile(
    rf"(?<![\w$])({_alternation(list(_PREFIX_CURRENCIES) + list(_CODES))})\s?({NUM}){_MONEY_MAGNITUDE}",
)
_MONEY_AFTER = _compile(
    rf"(?<![\w.])({NUM})(?:\s?({_MAGNITUDE_WORD})\b)?\s?"
    rf"((?:(?i:{_alternation(_SUFFIX_CURRENCIES)})|{_alternation(_CODES)})\b|[₫€])",
)


_CJK_CURRENCIES = {"元": None, "块": None, "令吉": "MYR", "马币": "MYR", "新币": "SGD", "美元": "USD",
                   "人民币": "CNY", "港币": "HKD", "日元": "JPY", "欧元": "EUR"}


_DOT_GROUPED = {"IDR", "VND"}
"""Currencies with no minor unit in use, written with dots between thousands: "Rp 50.000", "250.000₫"."""


def _dot_thousands(number: str, currency: str, magnitude: str | None) -> str:
    """"Rp 50.000" is fifty thousand. For every other currency one dot is a decimal point ("$0.125")."""
    if currency in _DOT_GROUPED and not magnitude and re.fullmatch(r"[1-9]\d{0,2}\.\d{3}", number):
        return number.replace(".", "")
    return number


def _money(text: str, words: Words) -> Iterator[Fact]:
    for m in _MONEY_BEFORE.finditer(text):
        symbol, number, word, suffix, letter = m.groups()
        currency = _currency(symbol)
        magnitude = word or suffix or letter
        value, numbers = scale(_dot_thousands(number, currency, magnitude), magnitude)
        yield Fact("money", m.start(), m.end(), m.group(), (currency, value), numbers)
    for m in _MONEY_AFTER.finditer(text):
        number, word, name = m.groups()
        currency = _currency(name)
        value, numbers = scale(_dot_thousands(number, currency, word), word)
        yield Fact("money", m.start(), m.end(), m.group(), (currency, value), numbers)
    if any(c in text for c in _CJK_CURRENCIES):
        for m in _CJK_MONEY.finditer(text):
            value = cjk_number(m.group(1))
            if m.group(3):
                value = EXACT.add(value, EXACT.divide(cjk_number(m.group(3)), Decimal(10)))
            if m.group(4):
                value = EXACT.add(value, EXACT.divide(cjk_number(m.group(4)), Decimal(100)))
            yield Fact("money", m.start(), m.end(), m.group(), (_CJK_CURRENCIES[m.group(2)], value), frozenset({value}))


# --------------------------------------------------------------------------- percent

_PERCENT = _compile(
    rf"(?<![\w.])({NUM})\s?(?:%|(?:percent|per cent|pct|percentage points?|percentage|peratus|persen)\b)", re.I
)


def _percents(text: str, words: Words) -> Iterator[Fact]:
    for m in _PERCENT.finditer(text):
        value = to_decimal(m.group(1))
        yield Fact("percent", m.start(), m.end(), m.group(), value, frozenset({value}))
    if "百分之" in text:
        for m in _CJK_PERCENT.finditer(text):
            value = cjk_number(m.group(1))
            yield Fact("percent", m.start(), m.end(), m.group(), value, frozenset({value}))


# ----------------------------------------------------------------------- temperature

_DEGREES = r"(?:\s?(?:°|º|˚|degrees?\s|deg\.?\s?)\s?(celsius|centigrade|fahrenheit|c|f)|((?-i:C|F)))\b"
_TEMPERATURE = _compile(
    rf"(?<![\w.])({NUM})(?:\s?(?:-|–|to)\s?({NUM}))?" + _DEGREES, re.I
)


def _temperatures(text: str, words: Words) -> Iterator[Fact]:
    """Temperatures with a stated scale. A range ("230-235°F") gives the scale to both ends."""
    for m in _TEMPERATURE.finditer(text):
        unit = (m.group(3) or m.group(4))[0].upper()
        ends = [(m.start(), m.end(), m.group(1))] if m.group(2) is None else [
            (m.start(1), m.end(1), m.group(1)), (m.start(2), m.end(), m.group(2))]
        for start, end, number in ends:
            value = to_decimal(number)
            yield Fact("temperature", start, end, text[start:end], (value, unit), frozenset({value}))


# ------------------------------------------------------------------------------ time

_MERIDIEM = r"(?:\s?(?:([ap])\.\s?m\.|([ap])\s?m\b|(pagi|petang|ptg|malam|(?:tengah|tgh)\s+hari)\b))"
"""AM/PM, and the Malay day-parts: pagi (morning), petang and malam (afternoon to night)."""
_CLOCK_CUE = _compile(r"\b(?:pukul|pkl|jam)\s*\Z", re.I)
"""A Malay day-part names a time only after a clock word or with minutes: "2 malam" is two nights."""
_CLOCK = _compile(
    rf"(?<![\w.,])(\d{{1,2}})(?::(\d{{2}}|0(?!\d))|\.(\d{{2}})(?={_MERIDIEM}))?(?::\d{{2}})?"
    rf"{_MERIDIEM}?(?!\w|:\d)",
    re.I,
)
"""A dot separates hours from minutes only before a meridiem: "9.30am" is a time, "9.30" a number."""
_CLOCK_WORD = _compile(r"\b(noon|midday|midnight)\b", re.I)


_CLOCK_RANGE_START = _compile(
    r"(?<![\w.,])(\d{1,2})(?::(\d{2}|0(?!\d)))?(?=\s?(?:-|–|to)\s?\d{1,2}(?::\d{2})?\s?(?:[ap]\.?\s?m\b))", re.I
)


def _times(text: str, words: Words) -> Iterator[Fact]:
    """Clock times. The Value is every 24-hour reading the text allows, as "HH:MM"."""
    for m in _CLOCK_RANGE_START.finditer(text):  # "5-9 pm": the 5 is a time too, AM or PM
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if 1 <= hour <= 12 and minute <= 59:
            yield Fact("time", m.start(), m.end(), m.group(), _clock_value({(hour % 12, minute), (hour % 12 + 12, minute)}))
    for m in _CLOCK.finditer(text):
        hour_s, colon_minute, dot_minute, _, _, _, dotted, plain, malay = m.groups()
        minute_s = colon_minute or dot_minute
        hour, minute = int(hour_s), int(minute_s or 0)
        part = re.sub(r"\s+", " ", malay.lower()) if malay else None
        if part == "malam" and minute_s is None and not _CLOCK_CUE.search(text[max(0, m.start() - 8):m.start()]):
            continue  # "2 malam" is two nights; "9 pagi" and "6 petang" are always times
        meridiem = dotted or plain or (part and _malay_meridiem(part, hour))
        if minute_s is None and meridiem is None:
            continue  # a bare number is a quantity, not a time
        if minute > 59 or hour > 24:
            continue
        if meridiem and (hour == 0 or hour > 12):
            meridiem = None  # "15:00 PM", "0:00 AM": the 24-hour clock wins over a stray meridiem
        if meridiem:
            readings = {(hour % 12 + (12 if meridiem.lower() == "p" else 0), minute)}
        elif hour == 0 or hour > 12:
            readings = {(hour % 24, minute)}
        else:
            readings = {(hour % 12, minute), (hour % 12 + 12, minute)}
            yield Fact("time", m.start(), m.end(), m.group(), _clock_value(readings),
                       as_24_hour=_clock_value({(hour, minute)}))
            continue
        yield Fact("time", m.start(), m.end(), m.group(), _clock_value(readings))
    if "点" in text:
        for m in _CJK_DAYPART_CLOCK.finditer(text):  # 上午9点, 下午3点半: the day part says AM or PM
            part, hour_s, half, minute_s, quarters = m.groups()
            hour = int(cjk_number(hour_s))
            minute = 30 if half else 15 * (1 if quarters == "一" else 3) if quarters else int(cjk_number(minute_s)) if minute_s else 0
            if hour > 24 or minute > 59:
                continue
            if 1 <= hour <= 12:
                pm = part in _CJK_PM and not (part == "晚上" and hour == 12)
                hour = hour % 12 + (12 if pm else 0)
            yield Fact("time", m.start(), m.end(), m.group(), _clock_value({(hour % 24, minute)}))
        for m in _CJK_CLOCK.finditer(text):
            hour_s, half, minute_s, quarters = m.groups()
            hour = int(cjk_number(hour_s))
            minute = 30 if half else 15 * (1 if quarters == "一" else 3) if quarters else int(cjk_number(minute_s))
            if hour > 24 or minute > 59:
                continue
            if 1 <= hour <= 12:
                yield Fact("time", m.start(), m.end(), m.group(), _clock_value({(hour % 12, minute), (hour % 12 + 12, minute)}),
                           as_24_hour=_clock_value({(hour, minute)}))
            else:
                yield Fact("time", m.start(), m.end(), m.group(), _clock_value({(hour % 24, minute)}))
    for m in _CLOCK_WORD.finditer(text):
        hour = 0 if m.group(1).lower() == "midnight" else 12
        yield Fact("time", m.start(), m.end(), m.group(), _clock_value({(hour, 0)}))


def _malay_meridiem(part: str, hour: int) -> str:
    """Pagi is AM; petang (ptg) and tengah hari (midday: 12 is noon) PM; malam PM except 12 malam, midnight."""
    return "p" if part in ("petang", "ptg", "tengah hari", "tgh hari") or (part == "malam" and hour != 12) else "a"


def _clock_value(readings: set[tuple[int, int]]) -> tuple[str, ...]:
    return tuple(sorted(f"{h:02d}:{m:02d}" for h, m in readings))


# -------------------------------------------------------------------------- quantity

_QUANTITY = _compile(rf"(?<![\w.])({NUM})(?:\s({_MAGNITUDE_WORD})\b|([kKMB]|(?i:bn|mn|tn))\b)?")


_VULGAR = {"½": "0.5", "¼": "0.25", "¾": "0.75", "⅛": "0.125", "⅜": "0.375", "⅝": "0.625", "⅞": "0.875",
           "⅕": "0.2", "⅖": "0.4", "⅗": "0.6", "⅘": "0.8"}
_FRACTION = _compile(rf"(?<![\w.])(\d*)\s?([{''.join(_VULGAR)}])")


def _fractions(text: str, words: Words) -> Iterator[Fact]:
    """"23½" is 23.5."""
    if not any(ch in text for ch in _VULGAR):
        return
    for m in _FRACTION.finditer(text):
        value = EXACT.add(Decimal(m.group(1) or 0), Decimal(_VULGAR[m.group(2)]))
        yield Fact("quantity", m.start(), m.end(), m.group(), value, frozenset({value}))


def _quantities(text: str, words: Words) -> Iterator[Fact]:
    for m in _QUANTITY.finditer(text):
        value, numbers = scale(m.group(1), m.group(2) or m.group(3))
        yield Fact("quantity", m.start(), m.end(), m.group(), value, numbers)


# ---------------------------------------------------------------------- number words

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
_SCALES = {"hundred": 100, **MAGNITUDE_WORDS}
_ORDINALS = {
    "first": "one", "second": "two", "third": "three", "fourth": "four", "fifth": "five", "sixth": "six",
    "seventh": "seven", "eighth": "eight", "ninth": "nine", "tenth": "ten", "eleventh": "eleven",
    "twelfth": "twelve", "thirteenth": "thirteen", "fourteenth": "fourteen", "fifteenth": "fifteen",
    "sixteenth": "sixteen", "seventeenth": "seventeen", "eighteenth": "eighteen", "nineteenth": "nineteen",
    "twentieth": "twenty", "thirtieth": "thirty", "fortieth": "forty", "fiftieth": "fifty", "sixtieth": "sixty",
    "seventieth": "seventy", "eightieth": "eighty", "ninetieth": "ninety", "hundredth": "hundred",
    "thousandth": "thousand", "millionth": "million",
}
_WORD = "|".join(sorted([*_UNITS, *_TENS, *_SCALES, *_ORDINALS, "dozen"], key=len, reverse=True))
_NUMBER_WORDS = _compile(rf"(?:an?\s+)?(?:{_WORD})(?:(?:\s+and\s+|[\s-]+)(?:{_WORD}))*\b", re.I)


def words_to_number(phrase: str) -> int | None:
    """``two hundred and fifty`` → 250. None when the words don't form one number."""
    words = [w for w in re.split(r"[\s-]+", phrase.lower()) if w and w != "and"]
    if any(w in _ORDINALS for w in words[:-1]):
        return None  # an ordinal can only end a number ("twenty-first")
    if words and words[-1] in _ORDINALS:
        if len(words) == 1 and _ORDINALS[words[0]] in _UNITS and _UNITS[_ORDINALS[words[0]]] < 10:
            return None  # "first", "second": far more often order or idiom than a count
        words[-1] = _ORDINALS[words[-1]]
    if words and words[0] in _SCALES:
        return None  # "the Million Man March": a scale needs a count ("a million", "two million")
    if words and words[0] in ("a", "an"):
        if len(words) < 2 or words[1] not in _SCALES and words[1] != "dozen":
            return None
        words[0] = "one"
    total = current = 0
    previous = None
    for w in words:
        if w == "dozen":
            current = (current or 1) * 12
        elif w in _UNITS or w in _TENS:
            value = _UNITS.get(w, _TENS.get(w))
            if previous in _UNITS or (previous in _TENS and value >= 10):
                return None  # "five six" and "twenty thirty" are two numbers, not one
            current += value
        elif w == "hundred":
            current = (current or 1) * 100
        else:
            total += (current or 1) * _SCALES[w]
            current = 0
        previous = w
    return total + current


_NUMBER_KEYWORDS = {*_UNITS, *_TENS, *_SCALES, *_ORDINALS, "dozen", "a", "an"}


def _number_words(text: str, words: Words) -> Iterator[Fact]:
    for m in _anchored(_NUMBER_WORDS, text, words, _NUMBER_KEYWORDS):
        value = words_to_number(m.group())
        if value is not None:
            yield Fact("quantity", m.start(), m.end(), m.group(), Decimal(value), frozenset({Decimal(value)}))
        elif _SPLITTABLE.search(m.group()):  # "fifteen and twenty", "first twenty": the longest valid runs
            yield from _number_word_runs(text, m.start(), m.end())
        # else "nineteen ninety nine", "Seven Eleven": a spoken year or a name, not two numbers


_SPLITTABLE = _compile(rf"^an?\s|\band\b|\b(?:{'|'.join(_ORDINALS)})\b", re.I)
"""Runs worth splitting: after an article ("a sixteen dollar glass"), at a connector, or at an ordinal."""
_LONGEST_NUMBER_PHRASE = 12
"""Tokens in the longest number phrase worth reading ("nine hundred and ninety nine thousand and one" is 8),
which keeps splitting a run linear however long the run is."""


def _number_word_runs(text: str, start: int, end: int) -> Iterator[Fact]:
    tokens = [(t.start(), t.end()) for t in _WORD_TOKEN.finditer(text, start, end)]
    i = 0
    while i < len(tokens):
        if text[tokens[i][0]:tokens[i][1]].lower() == "and":  # a connector never starts a number
            i += 1
            continue
        best = None
        for j in range(min(len(tokens), i + _LONGEST_NUMBER_PHRASE) - 1, i - 1, -1):
            phrase = text[tokens[i][0]:tokens[j][1]]
            value = words_to_number(phrase)
            if value is not None and not phrase.lower().endswith(" and"):
                best = (j, value, phrase)
                break
        if best is None:
            i += 1
            continue
        j, value, phrase = best
        yield Fact("quantity", tokens[i][0], tokens[j][1], phrase, Decimal(value), frozenset({Decimal(value)}))
        i = j + 1


def _is_small_word_count(fact: Fact) -> bool:
    """Spelled-out numbers below ten are not Claims, though they are still Evidence.

    Style guides spell out small counts, and in generated text they are usually counts
    the writer derived ("the two men", "three reviews") or idiom ("one of the best").
    Measured on RAGTruth train: +0.04 span precision for -0.01 hard-fact recall.
    """
    return fact.kind == "quantity" and fact.text[:1].isalpha() and fact.value < 10


# ------------------------------------------------------- Bahasa Melayu / Indonesia words

_MS_UNITS = {"satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5, "enam": 6, "tujuh": 7, "lapan": 8,
             "delapan": 8, "sembilan": 9}
_MS_SE = {"sepuluh": 10, "sebelas": 11, "seratus": 100, "seribu": 1000, "sejuta": 10**6}
_MS_MULTIPLIERS = {"belas": None, "puluh": 10, "ratus": 100}
_MS_WORD = "|".join(sorted([*_MS_UNITS, *_MS_SE, *_MS_MULTIPLIERS, *MALAY_MAGNITUDES], key=len, reverse=True))
_MS_NUMBER_WORDS = _compile(rf"(?:{_MS_WORD})(?:\s+(?:{_MS_WORD}))*\b", re.I)
_MS_KEYWORDS = {*_MS_UNITS, *_MS_SE}


def malay_words_to_number(phrase: str) -> int | None:
    """``dua ratus lima puluh`` → 250, ``sepuluh ribu`` → 10000."""
    total = current = 0
    pending: int | None = None
    for w in phrase.lower().split():
        if w in _MS_UNITS:
            if pending is not None:
                return None
            pending = _MS_UNITS[w]
        elif w in _MS_SE:
            value = _MS_SE[w]
            if value >= 1000:
                total += (current + (pending or 0) or 1) * value
                current, pending = 0, None
            else:
                current += value
        elif w == "belas":
            current += (pending or 1) + 10
            pending = None
        elif w in _MS_MULTIPLIERS:
            current += (pending or 1) * _MS_MULTIPLIERS[w]
            pending = None
        else:  # ribu, juta, bilion ...
            total += (current + (pending or 0) or 1) * MALAY_MAGNITUDES[w]
            current, pending = 0, None
    return total + current + (pending or 0)


def _malay_number_words(text: str, words: Words) -> Iterator[Fact]:
    for m in _anchored(_MS_NUMBER_WORDS, text, words, _MS_KEYWORDS):
        value = malay_words_to_number(m.group())
        if value:
            yield Fact("quantity", m.start(), m.end(), m.group(), Decimal(value), frozenset({Decimal(value)}))


# ------------------------------------------------------------------------ 中文 numerals

_CJK_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CJK_UNITS = {"十": 10, "百": 100, "千": 1000}
_CJK_BIG = {"万": 10**4, "亿": 10**8}
_CJK_CHARS = "".join([*_CJK_DIGITS, *_CJK_UNITS, *_CJK_BIG])
_CJK_NUMBER = (
    rf"(?:\d{{1,3}}(?:,\d{{3}})+|\d+)(?:\.\d+)?\s?[{''.join([*_CJK_UNITS, *_CJK_BIG])}]*(?![克米瓦卡])"
    rf"|[{_CJK_CHARS}]+(?:点[{''.join(_CJK_DIGITS)}]+[万亿]*(?![十分刻]))?"
)
_CJK_NUMERAL = _compile(rf"(?<![第{_CJK_CHARS}\d.,])({_CJK_NUMBER})")
_CJK_MONEY = _compile(rf"(?<![\d.,])({_CJK_NUMBER})\s?({_alternation(_CJK_CURRENCIES)})(?:(?<=[块元])([1-9一二两三四五六七八九])(?![0-9十百千万〇零一二两三四五六七八九])(?=[毛角钱]|[^一-鿿]|$)(?:[毛角](?:([1-9一二两三四五六七八九])(?![0-9十百千万〇零一二两三四五六七八九])(?=[分钱]|[^一-鿿]|$)分?)?)?)?")
"""八块五 and 八元五角 are 8.50, 十块五毛五 is 10.55: after 块 or 元 a lone digit counts tenths (毛, 角) and the
next hundredths (分), but only where no other word starts (三块五花肉 is three pieces of pork belly)."""
_CJK_PERCENT = _compile(rf"百分之({_CJK_NUMBER})")
_CJK_CLOCK_NUMBER = rf"(?:[{''.join(_CJK_DIGITS)}十]{{1,3}}|[0-9]{{1,2}})"
_CJK_CLOCK = _compile(rf"(?<![{_CJK_CHARS}0-9])({_CJK_CLOCK_NUMBER})点(?:(半)|({_CJK_CLOCK_NUMBER})分|([一三])刻)")
"""十一点五十分 (11:50), 三点半 (3:30), 八点一刻 (8:15). 点 is o'clock here, not a decimal point."""
_CJK_PM = ("中午", "下午", "傍晚", "晚上")
_CJK_DAYPART_CLOCK = _compile(
    rf"(上午|早上|凌晨|中午|下午|傍晚|晚上)\s?({_CJK_CLOCK_NUMBER})点(?:(半)|({_CJK_CLOCK_NUMBER})分|([一三])刻|钟)?")
"""上午9点 (9:00), 下午3点半 (15:30), 晚上8点 (20:00): with a day part, the hour alone is a time."""
_CJK_IDIOMS = ("十分", "万一", "千万", "一起", "一些", "一般", "一样", "一直", "一定", "一下", "一点", "一切", "统一", "唯一")


_SHORTHAND = {"百": 10, "千": 100, "万": 1000}
"""A lone last digit after 百, 千 or 万 counts the next unit down; after 零 (一万零五) it is ones."""


def cjk_number(token: str) -> Decimal:
    """``三千五百`` → 3500, ``1.2万`` → 12000, ``两百零五`` → 205."""
    lead = re.match(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", token)
    if lead:
        value = to_decimal(lead.group())
        for ch in token[lead.end():].strip():
            value = EXACT.multiply(value, Decimal(_CJK_UNITS.get(ch) or _CJK_BIG[ch]))
        return value
    if "点" in token:  # 一点五亿 = 1.5 × 10^8
        whole, _, rest = token.partition("点")
        fraction = "".join(str(_CJK_DIGITS[ch]) for ch in rest if ch in _CJK_DIGITS)
        value = EXACT.add(cjk_number(whole), Decimal(f"0.{fraction}"))
        for ch in rest[len(fraction):]:
            value = EXACT.multiply(value, Decimal(_CJK_BIG[ch]))
        return value
    total = section = number = 0
    for ch in token:
        if ch in _CJK_DIGITS:
            number = _CJK_DIGITS[ch]
        elif ch in _CJK_UNITS:
            section += (number or 1) * _CJK_UNITS[ch]
            number = 0
        elif ch == "万":
            total += ((section + number) or 1) * 10**4
            section = number = 0
        else:  # 亿 scales everything before it, so 一万亿 is 10^12
            total = (total + section + number or 1) * 10**8
            section = number = 0
    if number and len(token) > 1 and token[-2] in _SHORTHAND:  # 一万五 is 15000, 一百五 is 150
        number *= _SHORTHAND[token[-2]]
    return Decimal(total + section + number)


_CJK_ANY = _compile(f"[{_CJK_CHARS}]")


def _cjk_numbers(text: str, words: Words) -> Iterator[Fact]:
    if not _CJK_ANY.search(text):
        return
    numeral = set(_CJK_CHARS) | set("0123456789")
    for idiom in _CJK_IDIOMS:
        for m in re.finditer(idiom, text):
            before = text[m.start() - 1] if m.start() else ""
            after = text[m.end()] if m.end() < len(text) else ""
            if before not in numeral and after not in numeral:  # 十分 alone is "very"; 三十分钟 is 30 minutes
                yield Fact(EXEMPT, m.start(), m.end(), m.group(), None)
    for m in _CJK_NUMERAL.finditer(text):
        if not any(ch in _CJK_CHARS for ch in m.group()):
            continue  # plain digits are left to the quantity recogniser
        value = cjk_number(m.group())
        yield Fact("quantity", m.start(), m.end(), m.group(), value, frozenset({value}))


RECOGNISERS: list[Recogniser] = [
    _emails, _urls, _iso_datetimes, _dates, _last_digits, _phones, _money, _percents, _temperatures, _times, _identifiers, _cjk_numbers,
    _fractions, _quantities, _number_words, _malay_number_words,
]
SOURCE_RECOGNISERS: list[Recogniser] = [
    {_dates: _source_dates, _identifiers: _source_identifiers}.get(r, r) for r in RECOGNISERS]
"""Sources read a few forms more generously than Outputs do (ADR-0003): "May 19 and 20", and a
six-character code with no booking word near it (a long "reservations" list)."""


_ESCAPE = _compile(r"\\(?:\\|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|[nrtbf])")


_ONE_FOR_ONE = {
    **{cp: " " for cp in (0x00A0, 0x2007, 0x2009, 0x200A, 0x202F, 0x205F, 0x3000, *range(0x2002, 0x2007))},
    **{0xFF10 + i: str(i) for i in range(10)},                    # full-width digits
    **{0x0660 + i: str(i) for i in range(10)},                    # Arabic-Indic digits
    **{0x06F0 + i: str(i) for i in range(10)},                    # Extended Arabic-Indic digits
    **{0x0966 + i: str(i) for i in range(10)},                    # Devanagari digits
    **{0xFF21 + i: chr(0x41 + i) for i in range(26)},             # full-width A-Z
    **{0xFF41 + i: chr(0x61 + i) for i in range(26)},             # full-width a-z
    0xFF05: "%", 0xFF1A: ":", 0xFF04: "$", 0xFF0B: "+", 0xFF0D: "-", 0xFF0E: ".", 0x2212: "-",
}
"""Characters read as their ASCII twin. Every mapping is one character for one, so offsets hold."""


_NAME = _compile(r"(?<![\w.-])(?=[\w-]*[A-Za-z])(?=[\w-]*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*(?![\w-]|\.\d)")
"""A token mixing letters and digits: COVID-19, CD8, IL-4, H1N1, 13G, 4WD (ADR-0008)."""
_CURRENCY_CODE = _compile(r"(?:rm|rmb|usd|us|sgd|eur|gbp|jpy|cny|inr|idr|thb|php|vnd|aud|cad|hkd|nzd|rp|rs)\d", re.I)
"""An amount written against its currency code ("RMB105") is money, not a name."""


def names(text: str) -> list[tuple[int, int, str, str]]:
    """Every name in ``text`` as (start, end, surface, Value), scanned as extract() scans (ADR-0008)."""
    scan = _mask_escapes(text)
    return [(m.start(), m.end(), text[m.start():m.end()], name_value(m.group())) for m in _NAME.finditer(scan)
            if not _CURRENCY_CODE.match(m.group())]


_NAME_HYPHEN = _compile(r"(?<=[a-z])-(?=[0-9])|(?<=[0-9])-(?=[a-z])")


def name_value(token: str) -> str:
    """A name's Value: lower case, without a hyphen between a letter and a digit ("COVID-19" and
    "covid19" are one name; "X1-2" and "X12" are not)."""
    return _NAME_HYPHEN.sub("", token.lower())


def name_shape(value: str) -> str:
    """A name's shape: its Value with every run of digits as "#" ("covid#", "h#n#")."""
    return re.sub(r"[0-9]+", "#", value)


_MIDDLE_DOT_DECIMAL = _compile(r"(?<=[0-9])·(?=[0-9])")


def _mask_escapes(text: str) -> str:
    """Normalise the text that recognisers scan, keeping every offset.

    Escape sequences written as text are blanked: JSON renders a newline inside a
    string as backslash-n, and Python reprs write backslash-xa0, so a number right
    after one ("\\n40", "\\xa02018") would otherwise look glued to a word.
    Non-breaking and other Unicode spaces become spaces (CLDR puts U+202F before
    "PM"), and full-width or other-script digits become ASCII digits.
    """
    scan = text.translate(_ONE_FOR_ONE)
    if "\\" in scan:
        scan = _ESCAPE.sub(lambda m: " " * len(m.group()), scan)
    if "·" in scan:  # "37·8": the decimal point of The Lancet and other UK journals
        scan = _MIDDLE_DOT_DECIMAL.sub(".", scan)
    return scan


def extract(text: str, *, claims: bool = False) -> list[Fact]:
    """Hard facts in ``text``. With ``claims=True``, Exempt spans are skipped."""
    scan = _mask_escapes(text)
    taken = bytearray(len(text))
    words = _words(scan)
    facts: list[Fact] = []
    for recognise in [_exempt, *RECOGNISERS] if claims else SOURCE_RECOGNISERS:
        for fact in recognise(scan, words):
            if scan != text:
                fact = replace(fact, text=text[fact.start:fact.end])
            if any(taken[fact.start:fact.end]):
                continue
            taken[fact.start:fact.end] = b"\x01" * (fact.end - fact.start)
            facts.append(fact)
    facts = [f for f in facts if f.kind != EXEMPT and not (claims and _is_small_word_count(f))]
    facts.sort(key=lambda f: f.start)
    return _read_clock_style(scan, _spelled_amounts(scan, text, facts))


_MAJOR_UNIT = _compile(rf"\s+({_alternation(_SUFFIX_CURRENCIES)})\b", re.I)
_MINOR_JOIN = _compile(r"\s+(?:(?:and|dan)\s+)?", re.I)
_MINOR_UNIT = _compile(r"\s+(?:cents?|sen)\b", re.I)
_MINOR_ALONE = _compile(r"\s*(¢)|(?:\s+|-)(cents?|sen)\b", re.I)
"""A minor unit on its own is a hundredth: "50 sen" is RM0.50, "50 cents" and "50¢" are $0.50."""


def _spelled_amounts(scan: str, text: str, facts: list[Fact]) -> list[Fact]:
    """"one hundred forty-nine dollars and ninety cents", "RM149 dan 90 sen": one amount, as a voice
    agent writes it for text-to-speech. A number followed by a currency word is an amount, and
    "[and|dan] N cents/sen" (N under 100) adds its minor unit."""
    out: list[Fact] = []
    i = 0
    while i < len(facts):
        f = facts[i]
        currency, major, end = None, None, f.end
        if f.kind == "quantity":
            unit = _MAJOR_UNIT.match(scan, f.end)
            if unit:
                currency, major, end = _SUFFIX_CURRENCIES[unit.group(1).lower()], f.value, unit.end()
        elif f.kind == "money":
            currency, major = f.value
        if currency is None:
            alone = _MINOR_ALONE.match(scan, f.end) if f.kind == "quantity" else None
            if alone:
                amount = EXACT.divide(f.value, Decimal(100))
                unit = "MYR" if (alone.group(2) or "").lower() == "sen" else "$"
                out.append(Fact("money", f.start, alone.end(), text[f.start:alone.end()], (unit, amount), frozenset({amount, f.value})))
            else:
                out.append(f)
            i += 1
            continue
        nxt = facts[i + 1] if i + 1 < len(facts) else None
        join = _MINOR_JOIN.match(scan, end)
        minor_unit = nxt and _MINOR_UNIT.match(scan, nxt.end)
        if (join and nxt and nxt.kind == "quantity" and nxt.start == join.end() and minor_unit
                and nxt.value == nxt.value.to_integral_value() and 0 <= nxt.value < 100):
            amount = EXACT.add(major, EXACT.divide(nxt.value, Decimal(100)))
            stop = minor_unit.end()
            out.append(Fact("money", f.start, stop, text[f.start:stop], (currency, amount), frozenset({amount, major})))
            i += 2
            continue
        out.append(f if f.kind == "money" else Fact("money", f.start, end, text[f.start:end], (currency, major), frozenset({major})))
        i += 1
    return out


_TWENTY_FOUR_HOUR = _compile(r"(?<![\w.,:])(?:1[3-9]|2[0-3]):(?:\d{2}|0(?!\d))(?!\s?[ap]\.?\s?m\b)", re.I)


def _read_clock_style(text: str, facts: list[Fact]) -> list[Fact]:
    """A text that writes any 13:00-23:59 time is on the 24-hour clock, so its bare "9:00" is 09:00."""
    if not any(f.as_24_hour for f in facts) or not _TWENTY_FOUR_HOUR.search(text):
        return facts
    return [replace(f, value=f.as_24_hour) if f.as_24_hour else f for f in facts]
