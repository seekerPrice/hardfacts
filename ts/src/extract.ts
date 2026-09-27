/**
 * Find Hard facts in text and read their Values. A line-for-line port of the Python
 * reference (src/hardfacts/_extract.py); keep the two in step, and let the shared
 * fixture (test/fixture.json) catch any drift.
 *
 * Recognisers run in priority order. Each one claims the characters it matches, so a
 * later, looser recogniser can never re-read part of an earlier match.
 */

import { add, dec, type Dec, lessThan, mul } from "./decimal.ts";
import { alternation, compile, type Pattern, span } from "./regex.ts";

export type Value = Dec | string | (string | null)[];

export interface Fact {
  kind: string;
  start: number;
  end: number;
  text: string;
  value: Value;
  /** Plain numbers this Fact vouches for when it is Evidence for a bare quantity. */
  numbers: Set<Dec>;
  /** For a time written without AM/PM ("9:00"): its Value if the text is on the 24-hour clock. */
  as24Hour?: string[];
}

type Words = [number, string][];
type Recogniser = (text: string, words: Words) => Iterable<Fact>;

const EXEMPT = "exempt";

function fact(kind: string, start: number, end: number, text: string, value: Value, numbers: Iterable<Dec> = []): Fact {
  return { kind, start, end, text, value, numbers: new Set(numbers) };
}

function group(m: RegExpExecArray, g: number): string | undefined {
  return m[g] ?? undefined;
}

// --------------------------------------------------------------------------- numbers

const NUM = String.raw`(?<![\d,.])\d{1,3}\.\d{3},\d{1,2}(?!\d|[.,]\d|\])|\d{1,3}(?:\.\d{3}){2,}(?:,\d{1,2})?(?!\d|\.\d)|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+`;
export const MAGNITUDE_WORDS: Record<string, number> = {
  thousand: 1e3, lakh: 1e5, lakhs: 1e5, million: 1e6, crore: 1e7, crores: 1e7, billion: 1e9, trillion: 1e12,
};
const MALAY_MAGNITUDES: Record<string, number> = {
  ribu: 1e3, juta: 1e6, bilion: 1e9, miliar: 1e9, trilion: 1e12, triliun: 1e12,
};
const MONEY_SUFFIXES: Record<string, number> = { k: 1e3, m: 1e6, mn: 1e6, mil: 1e6, b: 1e9, bn: 1e9, t: 1e12, tn: 1e12 };
const MAGNITUDE_WORD = "(?i:thousand|lakhs?|million|crores?|billion|trillion|ribu|juta|bilion|miliar|trilion|triliun)";

const WORD_TOKEN = /[A-Za-z]+/g;

function words(text: string): Words {
  return [...text.matchAll(WORD_TOKEN)].map((m) => [m.index!, m[0].toLowerCase()]);
}

const ALNUM = /[\p{L}\p{N}_]/u;

/** The whole character before `pos`: a surrogate pair is one character, a lone surrogate is itself. */
function characterBefore(text: string, pos: number): string {
  const pair = pos >= 2 && /[\ud800-\udbff]/.test(text[pos - 2]) && /[\udc00-\udfff]/.test(text[pos - 1]);
  return pair ? text.slice(pos - 2, pos) : text[pos - 1];
}

/** `pattern` tried only at words that can start it: far cheaper than scanning a long Source. */
function* anchored(pattern: Pattern, text: string, ws: Words, keywords: Set<string>): Generator<RegExpExecArray> {
  let end = -1;
  for (const [pos, word] of ws) {
    if (pos < end || !keywords.has(word)) continue;
    if (pos && ALNUM.test(characterBefore(text, pos))) continue;
    const m = pattern.at(text, pos);
    if (m) {
      end = span(m)[1];
      yield m;
    }
  }
}

function scale(number: string, magnitude?: string): [Dec, Dec[]] {
  const base = dec(number);
  if (!magnitude) return [base, [base]];
  const word = magnitude.toLowerCase();
  const factor = MAGNITUDE_WORDS[word] ?? MALAY_MAGNITUDES[word] ?? MONEY_SUFFIXES[word];
  const value = mul(base, BigInt(factor));
  return [value, [value, base]];
}

// ----------------------------------------------------------------------- exempt spans

const LIST_MARKER = compile(String.raw`(?m)^[ \t]*(?:[-*•][ \t]*)?(?:step[ \t]+)?\d{1,3}(?:[.):]|[ \t]*[-–—:])(?=[ \t]|$)`, { ignoreCase: true });
const OUTPUT_LENGTH = compile(
  String.raw`\b(?:in|within|under|of|to|about|around|approximately|exactly|less than|fewer than|at most|no more than)` +
    String.raw`[ \t]+(?:about[ \t]+|around[ \t]+|approximately[ \t]+|exactly[ \t]+)?(\d{1,4})[ \t]+` +
    String.raw`(?:words?|sentences?|paragraphs?|bullet points?)\b`,
  { ignoreCase: true },
);
const N_WORD = compile(String.raw`\b\d{1,4}-(?:words?|sentences?|paragraphs?)\b`, { ignoreCase: true });
const EVERY_DAY = compile(
  String.raw`\b(?:seven|7)\s+days\s+a\s+week\b|\b24\s*/\s*7\b|\b24\s+hours\s+a\s+day\b|\b365\s+days\s+a\s+year\b`,
  { ignoreCase: true },
);
const HTML_ENTITY = compile(String.raw`&#?\w{1,8};`);
const RATING_SCALE = compile(String.raw`\bout\s+of\s+((?:5|10|100)(?:\.0)?)\b(?![.,]?\d)`, { ignoreCase: true });
const SELF_REFERENCE = compile(
  String.raw`\b(?:steps?|passages?|contexts?|reviews?|facts?|points?|tips?|methods?|options?)\s+` +
    String.raw`(\d{1,3}(?:\s*(?:,|and|or|&|-|–|to)\s*\d{1,3})*)\b`,
  { ignoreCase: true },
);
/**
 * A citation marker's shape: "[10]", "[1, 2, 5]", "[1-6]", "[^2]", "[Doc 3]", with at most six entries
 * of up to two digits each, so "[101, 102]" and "[2024]" are always values.
 */
const CITATION = compile(
  String.raw`\[(\^|(?:doc(?:ument)?|source|ref|context|passage)\s*)?\d{1,2}(?:\s*[,–-]\s*\^?\d{1,2}){0,5}\]`,
  { ignoreCase: true },
);
const CLOSES_A_CLAUSE = compile(String.raw`\s*(?:$|[.,;:!?)\[\n]|\s[A-Z])`);
const INTRODUCES_A_VALUE = new Set([
  "is", "are", "was", "were", "be", "been", "equals", "equal", "at", "to", "of", "in", "from", "between",
  "about", "around", "approximately", "only", "aged", "age", "ages", "seat", "seats", "answer", "coordinates",
  "values", "scores", "numbers", "ids", "list", "array", "vector", "range", "interval", "set", "takes", "take",
]);

/**
 * Citation markers close a clause: "were killed [10].", "the dominant language [2, 3, 5, 6] It".
 * A bracket that a value-introducing word leads into ("the scores were [7, 8, 9]", "seat [12] is") or
 * that sits in code or a list (":", "=", "{") is a value. "[^2]" and "[Doc 3]" are always citations.
 */
function* citations(text: string): Generator<Fact> {
  for (const m of CITATION.all(text)) {
    const [a, b] = span(m);
    if (!m[1]) {
      const before = codePointsBefore(text, a, 40).replace(/[ \t\n\r\f\v]+$/, "");
      const last = /([A-Za-z]+)$/.exec(before);
      if (!before || ":={(,[".includes(before[before.length - 1])
        || (last && INTRODUCES_A_VALUE.has(last[1].toLowerCase()))
        || CLOSES_A_CLAUSE.at(text, b) === null) continue;
    }
    yield fact(EXEMPT, a, b, m[0], null as unknown as string);
  }
}

const EXEMPTIONS: [Pattern, number][] = [
  [SELF_REFERENCE, 1], [RATING_SCALE, 1], [HTML_ENTITY, 0], [EVERY_DAY, 0], [LIST_MARKER, 0],
  [OUTPUT_LENGTH, 1], [N_WORD, 0],
];

function* exempt(text: string): Generator<Fact> {
  for (const [pattern, g] of EXEMPTIONS) {
    for (const m of pattern.all(text)) {
      const [a, b] = span(m, g);
      yield fact(EXEMPT, a, b, text.slice(a, b), null as unknown as string);
    }
  }
  yield* citations(text);
}

// ------------------------------------------------------------ contacts and identifiers

/** A URL character; a curly quote only inside a word ("/o’neill-jacket"), so “…/wapenc.” ends at the stop. */
const URL_CHAR = String.raw`[^\s<>"'()\[\]{}\u2018\u2019\u201c\u201d]` +
  String.raw`|[\u2018\u2019\u201c\u201d](?=[^\s<>"'()\[\]{}\u2018\u2019\u201c\u201d.,;:!?*\x60])`;
const URL_RE = compile(
  String.raw`(?:https?://|www\.)(?:${URL_CHAR})+` +
    String.raw`|(?<![\w.-])[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/(?:${URL_CHAR})*)?`,
  { ignoreCase: true },
);
/** Bare hosts are checked for a known TLD after matching, which keeps the pattern linear. */
const TLDS = new Set(["com", "org", "net", "io", "ai", "gov", "edu", "co", "my", "sg", "uk", "app", "dev", "info", "biz"]);
const EMAIL = compile(String.raw`(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+`);
const PHONE = compile(
  String.raw`(?<![\w+.,/-])(\+\d{1,3}[ .-]?)?(\(\d{1,4}\)[ .-]?)?(\d{1,4})((?:[ .-]\d{2,8}){1,4})(?![\w.,/-]?\d)`,
);
const PHONE_PLAIN = compile(String.raw`(?<![\w+.,/-])(?:\+\d{8,15}|0\d{8,10})(?![\w.,/-]?\d)`);
const PHONE_CUE = compile(
  String.raw`(?:\b(?:call|calls|phone|tel|telephone|hotline|whatsapp|mobile|fax|contact|sms|text|hubungi|telefon|nombor)\b` +
    String.raw`|电话|手机|联系|致电|拨打|热线|号码)[^\d\n]{0,15}$`,
  { ignoreCase: true },
);
const IDENTIFIER = compile(String.raw`(?<![\w#@/.-])#?(?=[A-Za-z0-9_/-]*\d)[A-Za-z0-9]+(?:[-_/][A-Za-z0-9]+)*(?![\w@])`);
const NOT_IDENTIFIER = compile(
  String.raw`\d+(?:\.\d+)?(?:st|nd|rd|th|s|x|k|kg|g|mg|lb|lbs|oz|km|m|cm|mm|mi|ft|in|mph|kph|kmh|hr|hrs|h|min|mins|` +
    String.raw`sec|secs|ms|am|pm|gb|mb|kb|tb|ghz|mhz|hz|w|kw|kwh|v|ml|l|cc|mp|p|fps|bn|mn|b|yr|yrs|d|wk|wks|D|` +
    String.raw`psi|rpm|kcal|cal|mah|db|ppm|mbps|gbps|kbps|lm|nm|mcg|iu|gal|qt|pt|tbsp|tsp|ha|sqft|ah|mw|gw)`,
  { ignoreCase: true },
);

/** An airline record locator ("XEHM8B"): six capitals and digits, often with a single digit. */
const BOOKING_CODE = compile(String.raw`[A-Z0-9]{6}`);
const BOOKING_CUE = compile(
  String.raw`\b(?:bookings?|reservations?|confirmations?|pnr|locator|ref|flights?|trips?|itinerar(?:y|ies)|tempahan)(?![a-z])` +
    String.raw`[^\n]{0,50}$`,
  { ignoreCase: true },
);
const NAME_SHAPED = compile(String.raw`[A-Z]{4,5}[0-9]{1,2}`);

/**
 * "XEHM8B" and "FDZ4T5" are codes; "LLAMA3", "BASE64" and "SAVE20" are names: letters, then a
 * version or amount. A name-shaped code is a code only after a booking word ("flight XEHM82").
 */
function isBookingCode(text: string, start: number, surface: string): boolean {
  if (!BOOKING_CODE.whole(surface)) return false;
  return !NAME_SHAPED.whole(surface) || BOOKING_CUE.search(codePointsBefore(text, start, 60)) !== null;
}

/** Digits an ID's segment needs before it counts as a stated number: account numbers, not ORD-2500. */
const STATED_SEGMENT = 6;

function stripTrailingPunctuation(m: RegExpExecArray): [number, number, string] {
  const surface = m[0].replace(/[.,;:!?]+$/, "");
  const start = span(m)[0];
  return [start, start + surface.length, surface];
}

export function normaliseUrl(url: string): string {
  return url.toLowerCase().replace(/^(?:https?:\/\/)?(?:www\.)?/, "").replace(/\/+$/, "");
}

const URL_HINTS = ["http", "www.", ".com", ".org", ".net", ".io", ".ai", ".gov", ".edu", ".co", ".my", ".sg", ".uk",
  ".app", ".dev", ".info", ".biz"];

function* urls(text: string): Generator<Fact> {
  const lowered = text.toLowerCase();
  if (!URL_HINTS.some((h) => lowered.includes(h))) return;
  for (const m of URL_RE.all(text)) {
    const surface = m[0].replace(/[.,;:!?*`]+$/, ""); // Markdown too: "**https://…/637**", "`app.vercel.app/tree`"
    const a = span(m)[0];
    let [end, kept] = [a + surface.length, surface];
    if (!/^(?:https?:\/\/|www\.)/i.test(surface)) {
      const host = surface.split("/", 1)[0];
      const known = knownHost(host.split("."));
      if (known === null) continue;
      if (known !== host) [end, kept] = [a + known.length, known]; // "HP.com.Click Support": a sentence joined on
    }
    yield fact("url", a, end, kept, normaliseUrl(kept));
  }
}

const SECOND_LEVEL = new Set(["com", "co", "org", "net", "gov", "edu", "ac"]);

/** The host a bare dotted name names, or null when its last label is no TLD ("report.pdf"). */
function knownHost(labels: string[]): string | null {
  const last = labels[labels.length - 1].toLowerCase();
  if (TLDS.has(last) || (labels.length >= 3 && /^[a-z]{2}$/.test(last) && SECOND_LEVEL.has(labels[labels.length - 2].toLowerCase()))) {
    return labels.join("."); // "example.com", "example.com.au", "foo.co.jp"
  }
  for (let k = labels.length - 2; k > 0; k--) {
    if (TLDS.has(labels[k].toLowerCase()) && /^[A-Z]/.test(labels[k + 1])) return labels.slice(0, k + 1).join(".");
  }
  return null;
}

function* emails(text: string): Generator<Fact> {
  if (!text.includes("@")) return;
  for (const m of EMAIL.all(text)) {
    const [a, b, surface] = stripTrailingPunctuation(m);
    yield fact("email", a, b, surface, surface.toLowerCase());
  }
}

/**
 * The 30 code points before `at`, one UTF-16 unit each (an emoji is one character, as in Python):
 * the cue window and its 15-character gap count what a reader counts.
 */
export function codePointsBefore(text: string, at: number, n: number): string {
  return Array.from(text.slice(Math.max(0, at - 2 * n), at)).slice(-n).map((c) => (c.length > 1 ? "\ufffd" : c)).join("");
}

function cued(text: string, at: number): boolean {
  return PHONE_CUE.search(codePointsBefore(text, at, 30)) !== null;
}

/**
 * Phones. A number grouped only by dots or spaces needs a country code, a trunk 0, the North
 * American 3-3-4 shape, or a cue word before it: dots and spaces also group thousands.
 */
function* phones(text: string): Generator<Fact> {
  for (const m of PHONE.all(text)) {
    const [a, b] = span(m);
    if (AFTER_CURRENCY.search(codePointsBefore(text, a, 8)) !== null) continue; // "$1.500.000" is money
    const [, country, area, first, rest] = m;
    const digits = m[0].replace(/\D/g, "");
    const groups = rest.replace(/^[ .-]+|[ .-]+$/g, "").split(/[ .-]+/).filter(Boolean);
    const lengths = [first.length, ...groups.map((g) => g.length)].join(",");
    const marked = Boolean(country || area);
    const trunk = first.startsWith("0") && digits.length >= 9 && digits.length <= 11;
    const nanp = lengths === "3,3,4" || lengths === "1,3,3,4"; // 212.555.0199, 1 800 555 0199
    const thousands = first.length <= 3 && groups.every((g) => g.length === 3);
    let ok: boolean;
    if (rest.includes("-")) {
      const shaped = groups.length >= 2 || (groups.length === 1 && (
        (first.startsWith("0") && groups[0].length >= 6 && groups[0].length <= 8) || (first.length === 3 && groups[0].length === 4)));
      ok = marked || shaped;
    } else {
      ok = marked || trunk || nanp || (!thousands && cued(text, a));
    }
    if (digits.length >= 7 && digits.length <= 15 && ok) yield fact("phone", a, b, m[0], digits);
  }
  for (const m of PHONE_PLAIN.all(text)) {
    const [a, b] = span(m);
    const digits = m[0].replace(/\D/g, "");
    if (m[0].startsWith("+") && !cued(text, a) && (digits.length < 10 || BEFORE_WORD.at(text, b) !== null)) continue; // "+12500000 this month"
    yield fact("phone", a, b, m[0], digits);
  }
}

const BEFORE_WORD = compile(String.raw`\s+[a-z]`);

/** What may stand for the hidden digits before the last ones: "ending in **1784", "…1863", "...1863". */
const ELLIPSIS = String.raw`(?:\*+|…|\.{3})?`;
const ENDING = compile(String.raw`\b(ending|ends)(?:\s+(?:in|with))?(?:\s*:)?\s*${ELLIPSIS}(\d{3,6})(?!\d|[.,]\d)`, { ignoreCase: true });
const ACCOUNT_CUE = compile(
  String.raw`\b(?:card|account|acct|number|no|phone|mobile|line|sim|id|visa|mastercard|amex|debit|credit|certificate|voucher|paypal|` +
    String.raw`kad|akaun|telefon)\b[^\n]{0,30}$`,
  { ignoreCase: true },
);
const TIME_NOUN = compile(
  String.raw`\b(?:years?|plan|contract|subscription|term|lease|period|season|promo(?:tion)?|offer|warranty|trial|` +
    String.raw`membership|quarter|month)\b`,
  { ignoreCase: true },
);
const YEAR_LIKE = compile(String.raw`(?:19|20)\d\d`);
/** A time noun closer to "ends in" than any card word: "card's promotional period ends in 2025". */
function timeIsNearer(window: string): boolean {
  const times = TIME_NOUN.all(window).map((m) => span(m)[0]);
  const cards = CARD_WORD.all(window).map((m) => span(m)[0]);
  return times.length > 0 && (cards.length === 0 || times[times.length - 1] > cards[cards.length - 1]);
}

/** A phone line that "ends in 2025" ends in that year; a line "ending in 2025" is named by its digits. */
const LINE_CUE = compile(String.raw`\b(?:line|sim)\b[^\n]{0,30}$`, { ignoreCase: true });
const CARD_WORD = compile(String.raw`\b(?:card|visa|mastercard|amex|debit|credit|kad)\b`, { ignoreCase: true });
/** Each run of spaces has one owner, so a failed match backtracks linearly (not "of" + 20,000 spaces). */
const LAST_N_DIGITS = compile(
  String.raw`\blast\s+(?:3|4|5|6|three|four|five|six)\s+(?:digits|numbers)(?:\s+of(?:\s+[a-z]+){1,4}?)?` +
    String.raw`(?:\s*(?::|\bis\b|\bare\b))?\s*${ELLIPSIS}(\d{3,6})(?!\d|[.,]\d)`,
  { ignoreCase: true },
);
/** A maximal run of mask characters, found left to right without rescanning: linear on 50 KB of "*". */
const MASK_RUN = compile(String.raw`[*xX•·](?:[*xX•· -]*[*xX•·])?`);
const AFTER_MASK = compile(String.raw`[ -]?(\d{3,6})(?!\d|[.,]\d)`);
/** Mask characters a card mask needs ("****", "xxxx", "•••"); two do when the digits touch ("••4242", "xx-4242"). */
const SMALLEST_MASK = 3;

/** "**500**" is Markdown bold and "•• 1200" a separator, not masks; "**** 4242" and "Visa ••4242" are. */
function isMask(marks: string[], gap: string, after: string): boolean {
  if (marks.every((ch) => ch === "*")) return marks.length >= SMALLEST_MASK && after !== "*";
  return marks.length >= SMALLEST_MASK || (marks.length === 2 && (gap === "" || gap === "-"));
}

/**
 * "The card ending in 1784", "last four digits are 5678", "**** 4242": the end of a longer number.
 * The Value is the digits after a "*" (`*1784`), a less specific statement of any number ending with them.
 * "Ending in" needs an account word before it, and a year after it is a year when a time word is near.
 */
function* lastDigits(text: string): Generator<Fact> {
  for (const m of ENDING.all(text)) {
    const window = codePointsBefore(text, span(m)[0], 40);
    if (ACCOUNT_CUE.search(window) === null) continue;
    // a time ("the trial on your account ends in 2025", "your line ends in 2025"), unless a card is named
    // ("Visa card ends in 2024") or the digits are masked ("line ends in …2025")
    if (YEAR_LIKE.whole(m[2]) && (timeIsNearer(window) || (
      m[1].toLowerCase() === "ends" && LINE_CUE.search(window) !== null && CARD_WORD.search(window) === null
      && !"*….".includes(text[span(m, 2)[0] - 1])))) continue;
    yield fact("identifier", ...span(m, 2), m[2], `*${m[2]}`);
  }
  for (const m of LAST_N_DIGITS.all(text)) yield fact("identifier", ...span(m, 1), m[1], `*${m[1]}`);
  if (![..."*xX•·"].some((ch) => text.includes(ch))) return;
  for (const run of MASK_RUN.all(text)) {
    const [a, b] = span(run);
    if (/[A-Za-z0-9]/.test(text[a - 1] ?? "")) continue;
    const m = AFTER_MASK.at(text, b);
    const marks = [...run[0]].filter((ch) => ch !== " " && ch !== "-");
    if (!m || !isMask(marks, text.slice(b, span(m, 1)[0]), text[span(m, 1)[1]] ?? "")) continue;
    yield fact("identifier", ...span(m, 1), m[1], `*${m[1]}`);
  }
}

const NUMBER_COMPOUND = compile(
  String.raw`\d+(?:\.\d+)?s?(?:-(?:[a-z]+|\d+(?:\.\d+)?))+` +
    String.raw`|[a-z]+-\d+(?:\.\d+)?s?` +
    String.raw`|\d+(?:\.\d+)?(?:[x×]\d+(?:\.\d+)?)+`,
);

/** A short word in a slash list: "etc", "LTE". A name with a digit ("i5", "M2") keeps the run a code. */
const LIST_ITEM = compile(String.raw`[A-Za-z]{1,3}`);

/**
 * "5G/4G/3G/2G" and "100Mbps/20Mbps" list alternatives or specs; each part is read on its own.
 *
 * Every part is a measure ("5G", "32GB") or a short word ("etc", "LTE"), and at least one is a
 * measure, so codes keep their slashes: "INV/2024/0012", "12A/12B", "A1/B2/C3", "i7/16GB/1TB".
 */
function isSlashList(surface: string): boolean {
  const parts = surface.split("/");
  if (parts.length < 2 || parts.some((p) => !p)) return false;
  const measures = parts.map((p) => NOT_IDENTIFIER.whole(p));
  return measures.some(Boolean) && parts.every((p, i) => measures[i] || LIST_ITEM.whole(p));
}

function sourceIdentifiers(text: string, ws: Words): Generator<Fact> {
  return identifiers(text, ws, true);
}

/** Codes mixing letters and digits. Short mixes ("COVID-19", "B12") are names, claimed as Exempt. */
function* identifiers(text: string, _ws?: Words, inSource = false): Generator<Fact> {
  for (const m of IDENTIFIER.all(text)) {
    const [a, b, surface] = stripTrailingPunctuation(m);
    const core = surface.replace(/[^A-Za-z0-9]/g, "");
    const digits = (core.match(/\d/g) ?? []).length;
    const letters = core.length - digits;
    if (!letters && digits >= 10 && !/^[.,]\d/.test(text.slice(b, b + 2))) {
      // FedEx, USPS, Amazon: long all-digit codes are IDs, not amounts (a decimal point says amount)
      yield fact("identifier", a, b, surface, core, [dec(core)]);
      continue;
    }
    if (NUMBER_COMPOUND.whole(surface) || isSlashList(surface)) continue;
    const isNumberTag = surface.startsWith("#") && /^\d+$/.test(core) && digits >= 3;
    if (!((letters && digits) || isNumberTag) || NOT_IDENTIFIER.whole(core)) continue;
    if (isNumberTag) {
      yield fact("identifier", a, b, surface, core, [dec(core)]); // "#48213" is the number 48213 with a tag
    } else if (digits >= 4 || (digits >= 3 && letters >= 2) || (inSource ? BOOKING_CODE.whole(surface) : isBookingCode(text, a, surface))) {
      // "credit_card_7574394" states the number 7574394; short segments ("ORD-2500") are labels
      const segments = surface.replace(/^#/, "").split(/[-_/]/)
        .filter((p) => /^[1-9]\d*$/.test(p) && p.length >= STATED_SEGMENT).map(dec);
      yield fact("identifier", a, b, surface, core.toUpperCase(), segments);
    } else {
      yield fact(EXEMPT, a, b, surface, "");
    }
  }
}

// ------------------------------------------------------------------------------ date

const MONTHS: Record<string, number> = {
  january: 1, jan: 1, february: 2, feb: 2, march: 3, mar: 3, april: 4, apr: 4,
  may: 5, june: 6, jun: 6, july: 7, jul: 7, august: 8, aug: 8, september: 9,
  sept: 9, sep: 9, october: 10, oct: 10, november: 11, nov: 11, december: 12, dec: 12,
  januari: 1, februari: 2, mac: 3, maret: 3, mei: 5, juni: 6, julai: 7, juli: 7,
  ogos: 8, agustus: 8, oktober: 10, okt: 10, disember: 12, desember: 12, dis: 12,
};
const MONTH_KEYWORDS = new Set(Object.keys(MONTHS));
const MONTH_NAMES = Object.keys(MONTHS).filter((m) => (m.length > 3 || ["may", "mac", "mei"].includes(m)) && m !== "sept");
const MONTH_ABBREVIATIONS = Object.keys(MONTHS).filter((m) => !MONTH_NAMES.includes(m));
const MONTH = `(${alternation(MONTH_NAMES)}|(?:${alternation(MONTH_ABBREVIATIONS)})(?![a-z])\\.?)`;
const DAY = String.raw`(\d{1,2})(?!\d)(?:st|nd|rd|th|hb)?`; // "hb": Malay haribulan, "3hb Oktober"
const YEAR = String.raw`(\d{4})`;
const ISO_DATE = compile(String.raw`(?<![\w.])(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?![\d])`);
const COMMA = String.raw`(?:\s?,\s*|\s+)`; // "July 22, 1947", tokenised text's "July 22 , 1947", and a contract's "October 1,1996"
/** A two-digit year only where a sentence could end ("3 Oct 26."), and never before a full year ("Oct 26, 2025"). */
const YEAR2 = String.raw`'?(\d{2})(?![.:]\d)(?=\s*(?:[.,;:)!?]|$))(?!\s*,?\s*\d{4})`;
const MONTH_FIRST = compile(String.raw`${MONTH}(?:\s+${DAY}(?!\s?%)(?:${COMMA}${YEAR})?|${COMMA}${YEAR})(?!\w|:\d)`, { ignoreCase: true });
/** Day and month one space apart on one line; a two-digit year never after a comma ("3 March, 45"). */
const DAY_FIRST = compile(String.raw`(?<![\w.])${DAY}[ \t](?:day\s+of\s+|of\s+)?${MONTH}(?:${COMMA}${YEAR}|[ \t]+${YEAR2})?(?!\w|:\d)`, { ignoreCase: true });
const DAY_FIRST_RANGE = compile(String.raw`(?<![\w.])${DAY}(?:\s?[-–]\s?|\s+(?:and|&|to)\s+)${DAY}[ \t](?:of\s+)?${MONTH}(?:${COMMA}${YEAR})?(?!\w|:\d)`, { ignoreCase: true });
const HYPHEN_DATE = compile(String.raw`(?<![\w.-])(\d{1,2})-${MONTH}-(\d{4}|\d{2})(?![\w-])`, { ignoreCase: true });
/** After the second day of "May 2nd and 3rd place": a rank, not a date. */
const NOT_A_DAY = String.raw`(?!\s+(?:place|grade|graders?|years?|floors?|rounds?|century|time|anniversary)\b)`;
/**
 * "March 10-12, 2015", and "May 19th and 20th": in an Output a word joins two days only when the
 * second is ordinal or a year follows ("May 27 and 28, 2024"), so "May 5 and 6 people" keeps its count.
 */
const DAY_RANGE = compile(
  String.raw`${MONTH}\s+${DAY}(?:\s?[-–]\s?|\s+(?:and|&|to)\s+(?=\d{1,2}(?:st|nd|rd|th)|\d{1,2}${COMMA}\d{4}(?!\d)))` +
    String.raw`${DAY}${NOT_A_DAY}(?:${COMMA}${YEAR})?(?!\w|:\d)`,
  { ignoreCase: true },
);
/**
 * A Source reads "May 19 and 20" as two dates too (Evidence may be generous: ADR-0003). The second day
 * also vouches for its number, so an Output's "6 people" still finds the 6 in "May 5 and 6 people".
 */
const DAY_RANGE_IN_SOURCE = compile(
  String.raw`${MONTH}\s+${DAY}(?:\s?[-–]\s?|\s+(?:and|&|to)\s+)${DAY}${NOT_A_DAY}(?:${COMMA}${YEAR})?(?!\w|:\d)`,
  { ignoreCase: true },
);
const NUMERIC_DATE = compile(String.raw`(?<![\w./])(\d{1,2})([/.])(\d{1,2})\2(\d{4})(?![\w/])`);
/**
 * "on 5/19", "by 22/05": a date without a year only when one part is over 12, so the order can't be
 * misread; "1/2", "5/6" and "24/7" stay what they were.
 */
const NUMERIC_MONTH_DAY = compile(String.raw`(?<![\w./])(\d{1,2})/(\d{1,2})(?![\w/]|[.,]\d|\s*%)`);
/**
 * A numeric month/day needs a date word before it: "on 5/19", "from 5/19 to 5/22". Without one,
 * "3/16 inch", "16/9" and "7/13 games" are fractions, and a Source's fraction must not vouch for a date.
 * A range to another date is date enough: "3/19 - 3/30/2017".
 */
/** Only these make "3/10" a date when either order could be one: "arrive 3/10", "on 10/3", "due 1/2". */
const STRONG_DATE_WORD = compile(String.raw`\b(?:on|dated?|due|expires?|expiring|departs?|departing|arrives?|arriving|returns?|returning|deliver(?:y|s|ed)?|ship(?:s|ped|ping)?|dispatch(?:ed)?|eta|sampai)\s*$`, { ignoreCase: true });
/** After "on 3/4" or "shipped 2/3": "of the days", "cup", "inch" make it a fraction. */
const FRACTION_OF = compile(String.raw`\s*(?:of\b|cups?\b|inch(?:es)?\b|hours?\b|miles?\b|teaspoons?\b|tablespoons?\b)`, { ignoreCase: true });
const TO_A_DATE = compile(String.raw`\s*(?:[-–]|to|through|thru|until)\s*\d{1,2}/\d{1,2}(?!\d)`, { ignoreCase: true });
const DATE_WORD = compile(
  String.raw`(?:\b(?:on|by|until|till|due|before|after|from|since|through|thru|to|and|dated?|valid|effective|expires?|expiring|` +
    String.raw`departs?|departing|arrives?|arriving|returns?|returning|starts?|starting|ends?|ending|` +
    String.raw`deliver(?:y|s|ed)?|ship(?:s|ped|ping)?|dispatch(?:ed)?|eta|sampai)|[-–])\s*$`,
  { ignoreCase: true },
);
const ISO_DATETIME = compile(
  String.raw`(?<![\w.])(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?(?!\w)`,
);

/** 2026-10-03T14:00:00+08:00: a date, a 24-hour time, and a tail (seconds, offset) that is neither. */
function* isoDatetimes(text: string): Generator<Fact> {
  for (const m of ISO_DATETIME.all(text)) {
    const [, year, month, day, hour, minute] = m;
    const date = dateValue(year, month, day);
    if (date === null || Number(hour) > 23 || Number(minute) > 59) continue;
    const [ds, de] = [span(m, 1)[0], span(m, 3)[1]];
    yield fact("date", ds, de, text.slice(ds, de), [date], [dec(year)]);
    const [ts, te] = [span(m, 4)[0], span(m, 5)[1]];
    yield fact("time", ts, te, text.slice(ts, te), clockValue([[Number(hour), Number(minute)]]));
    if (te < span(m)[1]) yield fact(EXEMPT, te, span(m)[1], text.slice(te, span(m)[1]), "");
  }
}

const CJK_DATE = compile(String.raw`(?:(\d{4})\s?年\s?)?(\d{1,2})\s?月(?:\s?(\d{1,2})\s?[日号])?`);

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** EDTF-style "YYYY-MM-DD" with X for unstated parts, or null when out of range. */
function dateValue(year: string | undefined, month: string | number | undefined, day: string | undefined): string | null {
  const y = year ? Number(year) : null;
  const m = typeof month === "number" ? month
    : month && /^\d+$/.test(month) ? Number(month)
    : MONTHS[(month ?? "").toLowerCase().replace(/\.+$/, "")];
  const d = day ? Number(day) : null;
  if ((y !== null && (y < 1000 || y > 2999)) || m === undefined || m < 1 || m > 12 || (d !== null && (d < 1 || d > 31))) {
    return null;
  }
  return `${y ?? "XXXX"}-${pad(m)}-${d ? pad(d) : "XX"}`;
}

/** A date Fact; it vouches for its years, and for `also`. */
function dateFact(text: string, start: number, end: number, readings: (string | null)[], also: Dec[] = []): Fact | null {
  const values = [...new Set(readings.filter((r): r is string => Boolean(r)))].sort();
  if (!values.length) return null;
  const years = values.filter((r) => r[0] !== "X").map((r) => dec(r.slice(0, 4)));
  return fact("date", start, end, text.slice(start, end), values, [...years, ...also]);
}

function sourceDates(text: string, ws: Words): Generator<Fact> {
  return dates(text, ws, true);
}

function* dates(text: string, ws: Words, inSource = false): Generator<Fact> {
  const found: [number, number, (string | null)[], Dec[]?][] = [];
  if (text.includes("月")) {
    for (const m of CJK_DATE.all(text)) {
      const [, year, month, day] = m;
      if (year || day) found.push([...span(m), [dateValue(year, Number(month), day)]]);
    }
  }
  for (const m of ISO_DATE.all(text)) found.push([...span(m), [dateValue(m[1], m[2], m[3])]]);
  for (const m of anchored(inSource ? DAY_RANGE_IN_SOURCE : DAY_RANGE, text, ws, MONTH_KEYWORDS)) { // both ends are dates
    const [, month, first, last, year] = m;
    found.push([span(m)[0], span(m, 2)[1], [dateValue(year, month, first)]]);
    // in a Source, the second day of "May 5 and 6" also vouches for its number (a count may follow);
    // of "March 10-12" it doesn't
    const worded = inSource && /\band\b|&/i.test(text.slice(span(m, 2)[1], span(m, 3)[0])); // not "10 to 12"
    found.push([span(m, 3)[0], span(m)[1], [dateValue(year, month, last)], worded ? [dec(last)] : []]);
  }
  for (const m of anchored(MONTH_FIRST, text, ws, MONTH_KEYWORDS)) {
    const [, month, day, yearAfterDay, yearAlone] = m;
    if (isAppleMac(text, month, span(m)[1])) continue;
    found.push([...span(m), [dateValue(yearAfterDay || yearAlone, month, day)]]);
  }
  for (const m of DAY_FIRST_RANGE.all(text)) { // "3–5 October 2026": both ends are dates
    const [, first, last, month, year] = m;
    found.push([span(m)[0], span(m, 1)[1], [dateValue(year, month, first)]]);
    found.push([span(m, 2)[0], span(m)[1], [dateValue(year, month, last)]]);
  }
  for (const m of DAY_FIRST.all(text)) {
    const [, day, month, year, year2] = m;
    if (isAppleMac(text, month, span(m)[1])) continue;
    found.push([...span(m), [dateValue(year || fullYear(year2), month, day)]]);
  }
  for (const m of HYPHEN_DATE.all(text)) { // "3-Oct-2026", "03-OCT-26"
    const [, day, month, year] = m;
    found.push([...span(m), [dateValue(fullYear(year), month, day)]]);
  }
  for (const m of NUMERIC_MONTH_DAY.all(text)) {
    const [a, b] = [Number(m[1]), Number(m[2])];
    const start = span(m)[0];
    const before = codePointsBefore(text, start, 20);
    if ((a > 12 && b > 12) || !a || !b || (DATE_WORD.search(before) === null && TO_A_DATE.at(text, span(m)[1]) === null)) {
      continue; // "13/20" is neither; "3/16 inch" has no date word
    }
    if (a <= 12 && b <= 12 && (STRONG_DATE_WORD.search(before) === null || FRACTION_OF.at(text, span(m)[1]) !== null)) {
      continue; // "after 1/2 hour", "and 1/4 cup": either order is a fraction first
    }
    // "arrive 3/10" is 3 October in Malaysia and 10 March in the US: both readings, doubt is Supported
    const readings: [number, number][] = b > 12 ? [[a, b]] : a > 12 ? [[b, a]] : [[a, b], [b, a]];
    found.push([...span(m), readings.map(([month, day]) => dateValue(undefined, month, String(day))),
      inSource ? [dec(String(a)), dec(String(b))] : []]);
  }
  for (const m of NUMERIC_DATE.all(text)) {
    const [, a, , b, year] = m;
    found.push([...span(m), [dateValue(year, Number(b), a), dateValue(year, Number(a), b)]]);
  }
  const facts = found.map(([start, end, values, also]) => dateFact(text, start, end, values, also)).filter((f): f is Fact => f !== null);
  // Of two overlapping readings the one stating more is right; then the earliest, then the longest.
  facts.sort((x, y) => statedParts(y) - statedParts(x) || x.start - y.start || (y.end - y.start) - (x.end - x.start));
  yield* facts;
}

/** How many of year, month and day the Fact's least specific reading states. */
function statedParts(f: Fact): number {
  return Math.min(...(f.value as string[]).map((r) => r.split("-").filter((part) => part[0] !== "X").length));
}

/** "26" → "2026", "85" → "1985": the POSIX pivot (69-99 are 19xx). */
function fullYear(year: string | undefined): string | undefined {
  if (!year || year.length === 4) return year;
  return `${Number(year) >= 69 ? 19 : 20}${year}`;
}

const APPLE_NOUN = compile(String.raw`\s+(?:laptops?|book|pro|mini|air|os|computers?|users?|apps?|address|store|studio)\b`, { ignoreCase: true });

/** "5 Mac laptops" is a computer; "5 Mac" is Malay for 5 March. */
function isAppleMac(text: string, month: string, end: number): boolean {
  return month.toLowerCase() === "mac" && APPLE_NOUN.at(text, end) !== null;
}

// ----------------------------------------------------------------------------- money

export const PREFIX_CURRENCIES: Record<string, string> = {
  "US$": "USD", "S$": "SGD", "A$": "AUD", "C$": "CAD", "HK$": "HKD", "NZ$": "NZD", "$": "$",
  "€": "EUR", "£": "GBP", "¥": "¥", "₹": "INR", "₱": "PHP", "₫": "VND", "฿": "THB",
  RM: "MYR", Rp: "IDR", "Rs.": "INR", Rs: "INR",
};
export const CODES = ["USD", "SGD", "MYR", "EUR", "GBP", "JPY", "CNY", "RMB", "INR", "IDR", "THB", "PHP", "VND", "AUD", "CAD", "HKD", "NZD"];
export const SUFFIX_CURRENCIES: Record<string, string> = {
  dollar: "$", dollars: "$", ringgit: "MYR", euro: "EUR", euros: "EUR", yen: "JPY",
  yuan: "CNY", rupee: "INR", rupees: "INR", baht: "THB", peso: "PHP", pesos: "PHP",
  rupiah: "IDR", dong: "VND",
};
export const DOLLAR_FAMILY = new Set(["$", "USD", "SGD", "AUD", "CAD", "HKD", "NZD"]);
export const YEN_FAMILY = new Set(["¥", "JPY", "CNY"]);
const CJK_CURRENCIES: Record<string, string | null> = {
  "元": null, "块": null, "令吉": "MYR", "马币": "MYR", "新币": "SGD", "美元": "USD",
  "人民币": "CNY", "港币": "HKD", "日元": "JPY", "欧元": "EUR",
};

export function currency(token: string): string {
  const code = PREFIX_CURRENCIES[token] ?? SUFFIX_CURRENCIES[token.toLowerCase()] ?? token.toUpperCase();
  return code === "RMB" ? "CNY" : code;
}

const MONEY_MAGNITUDE = String.raw`(?:\s?(${MAGNITUDE_WORD})\b|\s?((?i:mil|bn|mn|tn))\b|((?i:[kmbt]))(?!\w|-(?!RM|Rp|Rs|[A-Z]{1,2}\$)[A-Za-z]))?`;
/**
 * Thousands grouped by spaces, read only right after a currency sign: "$97 884", "£244 200" (The Lancet).
 * Plain numbers keep their spaces as separators: "Table 2 100 patients" is 2 and 100.
 */
const SPACE_GROUPED = String.raw`\d{1,3}(?: \d{3})+(?![\d.,]?\d)`;
const MONEY_BEFORE = compile(
  String.raw`(?<![\w$])(${alternation([...Object.keys(PREFIX_CURRENCIES), ...CODES])})\s?(${SPACE_GROUPED}|${NUM})${MONEY_MAGNITUDE}`,
);
const MONEY_AFTER = compile(
  String.raw`(?<![\w.])(${NUM})(?:\s?(${MAGNITUDE_WORD})\b)?\s?` +
    String.raw`((?:(?i:${alternation(Object.keys(SUFFIX_CURRENCIES))})|${alternation(CODES)})\b|[₫€])`,
);
const AFTER_CURRENCY = compile(String.raw`(?:${alternation([...Object.keys(PREFIX_CURRENCIES), ...CODES])})\s?$`);

/** Currencies with no minor unit in use, written with dots between thousands: "Rp 50.000", "250.000₫". */
const DOT_GROUPED = new Set(["IDR", "VND"]);

/** "Rp 50.000" is fifty thousand. For every other currency one dot is a decimal point ("$0.125"). */
function dotThousands(number: string, code: string, magnitude: string | undefined): string {
  return DOT_GROUPED.has(code) && !magnitude && /^[1-9]\d{0,2}\.\d{3}$/.test(number) ? number.replace(".", "") : number;
}

function* money(text: string): Generator<Fact> {
  for (const m of MONEY_BEFORE.all(text)) {
    const [, symbol, number, word, suffix, letter] = m;
    const code = currency(symbol);
    const magnitude = word || suffix || letter;
    const [value, numbers] = scale(dotThousands(number.replace(/ /g, ""), code, magnitude), magnitude);
    yield fact("money", ...span(m), m[0], [code, value], numbers);
  }
  for (const m of MONEY_AFTER.all(text)) {
    const [, number, word, name] = m;
    const code = currency(name);
    const [value, numbers] = scale(dotThousands(number, code, word), word);
    yield fact("money", ...span(m), m[0], [code, value], numbers);
  }
  if (Object.keys(CJK_CURRENCIES).some((c) => text.includes(c))) {
    for (const m of CJK_MONEY.all(text)) {
      let value = cjkNumber(m[1]);
      if (m[3]) value = add(value, dec(`0.${cjkNumber(m[3])}`));
      if (m[4]) value = add(value, dec(`0.0${cjkNumber(m[4])}`));
      yield fact("money", ...span(m), m[0], [CJK_CURRENCIES[m[2]], value], [value]);
    }
  }
}

// --------------------------------------------------------------------------- percent

const PERCENT = compile(
  String.raw`(?<![\w.])(${NUM})\s?(?:%|(?:percent|per cent|pct|percentage points?|percentage|peratus|persen)\b)`,
  { ignoreCase: true },
);

function* percents(text: string): Generator<Fact> {
  for (const m of PERCENT.all(text)) {
    const value = dec(m[1]);
    yield fact("percent", ...span(m), m[0], value, [value]);
  }
  if (text.includes("百分之")) {
    for (const m of CJK_PERCENT.all(text)) {
      const value = cjkNumber(m[1]);
      yield fact("percent", ...span(m), m[0], value, [value]);
    }
  }
}

// ----------------------------------------------------------------------- temperature

const DEGREES = String.raw`(?:\s?(?:°|º|˚|degrees?\s|deg\.?\s?)\s?(celsius|centigrade|fahrenheit|c|f)|((?-i:C|F)))\b`;
const TEMPERATURE = compile(String.raw`(?<![\w.])(${NUM})(?:\s?(?:-|–|to)\s?(${NUM}))?` + DEGREES, { ignoreCase: true });

function* temperatures(text: string): Generator<Fact> {
  for (const m of TEMPERATURE.all(text)) {
    const unit = (m[3] || m[4])[0].toUpperCase();
    const ends: [number, number, string][] = m[2] === undefined
      ? [[...span(m), m[1]]]
      : [[...span(m, 1), m[1]], [span(m, 2)[0], span(m)[1], m[2]]];
    for (const [a, b, number] of ends) {
      const value = dec(number);
      yield fact("temperature", a, b, text.slice(a, b), [value, unit], [value]);
    }
  }
}

// ------------------------------------------------------------------------------ time

const MERIDIEM = String.raw`(?:\s?(?:([ap])\.\s?m\.|([ap])\s?m\b|(pagi|petang|ptg|malam|(?:tengah|tgh)\s+hari)\b))`;
const CLOCK = compile(
  String.raw`(?<![\w.,])(\d{1,2})(?::(\d{2}|0(?!\d))|\.(\d{2})(?=${MERIDIEM}))?(?::\d{2})?` +
    String.raw`${MERIDIEM}?(?!\w|:\d)`,
  { ignoreCase: true },
);
/** A Malay day-part names a time only after a clock word or with minutes: "2 malam" is two nights. */
const CLOCK_CUE = compile(String.raw`\b(?:pukul|pkl|jam)\s*$`, { ignoreCase: true });
const CLOCK_WORD = compile(String.raw`\b(noon|midday|midnight)\b`, { ignoreCase: true });
const CLOCK_RANGE_START = compile(
  String.raw`(?<![\w.,])(\d{1,2})(?::(\d{2}|0(?!\d)))?(?=\s?(?:-|–|to)\s?\d{1,2}(?::\d{2})?\s?(?:[ap]\.?\s?m\b))`,
  { ignoreCase: true },
);

/** Pagi is AM, petang PM, and malam PM except 12 malam, which is midnight. */
function malayMeridiem(part: string, hour: number): string {
  return ["petang", "ptg", "tengah hari", "tgh hari"].includes(part) || (part === "malam" && hour !== 12) ? "p" : "a";
}

function clockValue(readings: [number, number][]): string[] {
  return [...new Set(readings.map(([h, m]) => `${pad(h)}:${pad(m)}`))].sort();
}

function* times(text: string): Generator<Fact> {
  for (const m of CLOCK_RANGE_START.all(text)) {
    const hour = Number(m[1]);
    const minute = Number(m[2] ?? 0);
    if (hour >= 1 && hour <= 12 && minute <= 59) {
      yield fact("time", ...span(m), m[0], clockValue([[hour % 12, minute], [hour % 12 + 12, minute]]));
    }
  }
  for (const m of CLOCK.all(text)) {
    const [, hourS, colonMinute, dotMinute, , , , dotted, plain, malay] = m;
    const minuteS = colonMinute ?? dotMinute;
    const hour = Number(hourS);
    const minute = Number(minuteS ?? 0);
    const part = malay ? malay.toLowerCase().replace(/[ \t\n\r\f\v]+/g, " ") : undefined;
    // "2 malam" is two nights; "9 pagi" and "6 petang" are always times
    if (part === "malam" && minuteS === undefined && CLOCK_CUE.search(codePointsBefore(text, span(m)[0], 8)) === null) continue;
    let meridiem: string | undefined = dotted || plain || (part ? malayMeridiem(part, hour) : undefined);
    if (minuteS === undefined && !meridiem) continue;
    if (minute > 59 || hour > 24) continue;
    if (meridiem && (hour === 0 || hour > 12)) meridiem = undefined;
    if (meridiem) {
      yield fact("time", ...span(m), m[0], clockValue([[hour % 12 + (meridiem.toLowerCase() === "p" ? 12 : 0), minute]]));
    } else if (hour === 0 || hour > 12) {
      yield fact("time", ...span(m), m[0], clockValue([[hour % 24, minute]]));
    } else {
      const f = fact("time", ...span(m), m[0], clockValue([[hour % 12, minute], [hour % 12 + 12, minute]]));
      f.as24Hour = clockValue([[hour, minute]]);
      yield f;
    }
  }
  if (text.includes("点")) {
    for (const m of CJK_DAYPART_CLOCK.all(text)) { // 上午9点, 下午3点半: the day part says AM or PM
      const [, part, hourS, half, minuteS, quarters] = m;
      let hour = Number(cjkNumber(hourS));
      const minute = half ? 30 : quarters ? 15 * (quarters === "一" ? 1 : 3) : minuteS ? Number(cjkNumber(minuteS)) : 0;
      if (hour > 24 || minute > 59) continue;
      if (hour >= 1 && hour <= 12) {
        const pm = CJK_PM.has(part) && !(part === "晚上" && hour === 12);
        hour = hour % 12 + (pm ? 12 : 0);
      }
      yield fact("time", ...span(m), m[0], clockValue([[hour % 24, minute]]));
    }
    for (const m of CJK_CLOCK.all(text)) {
      const [, hourS, half, minuteS, quarters] = m;
      const hour = Number(cjkNumber(hourS));
      const minute = half ? 30 : quarters ? 15 * (quarters === "一" ? 1 : 3) : Number(cjkNumber(minuteS));
      if (hour > 24 || minute > 59) continue;
      if (hour >= 1 && hour <= 12) {
        const f = fact("time", ...span(m), m[0], clockValue([[hour % 12, minute], [hour % 12 + 12, minute]]));
        f.as24Hour = clockValue([[hour, minute]]);
        yield f;
      } else {
        yield fact("time", ...span(m), m[0], clockValue([[hour % 24, minute]]));
      }
    }
  }
  for (const m of CLOCK_WORD.all(text)) {
    const hour = m[1].toLowerCase() === "midnight" ? 0 : 12;
    yield fact("time", ...span(m), m[0], clockValue([[hour, 0]]));
  }
}

// -------------------------------------------------------------------------- quantity

const QUANTITY = compile(String.raw`(?<![\w.])(${NUM})(?:\s(${MAGNITUDE_WORD})\b|([kKMB]|(?i:bn|mn|tn))\b)?`);
const VULGAR: Record<string, string> = {
  "½": "0.5", "¼": "0.25", "¾": "0.75", "⅛": "0.125", "⅜": "0.375", "⅝": "0.625", "⅞": "0.875",
  "⅕": "0.2", "⅖": "0.4", "⅗": "0.6", "⅘": "0.8",
};
const FRACTION = compile(String.raw`(?<![\w.])(\d*)\s?([${Object.keys(VULGAR).join("")}])`);

function* fractions(text: string): Generator<Fact> {
  if (!Object.keys(VULGAR).some((c) => text.includes(c))) return;
  for (const m of FRACTION.all(text)) {
    const value = add(dec(m[1] || "0"), VULGAR[m[2]]);
    yield fact("quantity", ...span(m), m[0], value, [value]);
  }
}

function* quantities(text: string): Generator<Fact> {
  for (const m of QUANTITY.all(text)) {
    const [value, numbers] = scale(m[1], group(m, 2) || group(m, 3));
    yield fact("quantity", ...span(m), m[0], value, numbers);
  }
}

// ---------------------------------------------------------------------- number words

const UNITS: Record<string, number> = Object.fromEntries(
  "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen"
    .split(" ").map((w, i) => [w, i]),
);
const TENS: Record<string, number> = Object.fromEntries(
  "twenty thirty forty fifty sixty seventy eighty ninety".split(" ").map((w, i) => [w, 10 * (i + 2)]),
);
const SCALES: Record<string, number> = { hundred: 100, ...MAGNITUDE_WORDS };
const ORDINALS: Record<string, string> = {
  first: "one", second: "two", third: "three", fourth: "four", fifth: "five", sixth: "six",
  seventh: "seven", eighth: "eight", ninth: "nine", tenth: "ten", eleventh: "eleven",
  twelfth: "twelve", thirteenth: "thirteen", fourteenth: "fourteen", fifteenth: "fifteen",
  sixteenth: "sixteen", seventeenth: "seventeen", eighteenth: "eighteen", nineteenth: "nineteen",
  twentieth: "twenty", thirtieth: "thirty", fortieth: "forty", fiftieth: "fifty", sixtieth: "sixty",
  seventieth: "seventy", eightieth: "eighty", ninetieth: "ninety", hundredth: "hundred",
  thousandth: "thousand", millionth: "million",
};
const WORD = alternation([...Object.keys(UNITS), ...Object.keys(TENS), ...Object.keys(SCALES), ...Object.keys(ORDINALS), "dozen"]);
const NUMBER_WORDS = compile(String.raw`(?:an?\s+)?(?:${WORD})(?:(?:\s+and\s+|[\s-]+)(?:${WORD}))*\b`, { ignoreCase: true });
const NUMBER_KEYWORDS = new Set([...Object.keys(UNITS), ...Object.keys(TENS), ...Object.keys(SCALES), ...Object.keys(ORDINALS), "dozen", "a", "an"]);

/** "two hundred and fifty" → 250n. null when the words don't form one number. */
export function wordsToNumber(phrase: string): bigint | null {
  const ws = phrase.toLowerCase().split(/[\s-]+/).filter((w) => w && w !== "and");
  if (ws.slice(0, -1).some((w) => w in ORDINALS)) return null;
  const last = ws[ws.length - 1];
  if (ws.length && last in ORDINALS) {
    if (ws.length === 1 && ORDINALS[last] in UNITS && UNITS[ORDINALS[last]] < 10) return null;
    ws[ws.length - 1] = ORDINALS[last];
  }
  if (ws.length && ws[0] in SCALES) return null;
  if (ws.length && (ws[0] === "a" || ws[0] === "an")) {
    if (ws.length < 2 || (!(ws[1] in SCALES) && ws[1] !== "dozen")) return null;
    ws[0] = "one";
  }
  let total = 0n;
  let current = 0n;
  let previous: string | null = null;
  for (const w of ws) {
    if (w === "dozen") {
      current = (current || 1n) * 12n;
    } else if (w in UNITS || w in TENS) {
      const value = UNITS[w] ?? TENS[w];
      if ((previous !== null && previous in UNITS) || (previous !== null && previous in TENS && value >= 10)) return null;
      current += BigInt(value);
    } else if (w === "hundred") {
      current = (current || 1n) * 100n;
    } else {
      total += (current || 1n) * BigInt(SCALES[w]);
      current = 0n;
    }
    previous = w;
  }
  return total + current;
}

function* numberWords(text: string, ws: Words): Generator<Fact> {
  for (const m of anchored(NUMBER_WORDS, text, ws, NUMBER_KEYWORDS)) {
    const value = wordsToNumber(m[0]);
    if (value !== null) {
      const d = dec(value.toString());
      yield fact("quantity", ...span(m), m[0], d, [d]);
    } else if (SPLITTABLE.search(m[0]) !== null) { // "fifteen and twenty", "first twenty": the longest valid runs
      yield* numberWordRuns(text, ...span(m));
    } // else "nineteen ninety nine", "Seven Eleven": a spoken year or a name, not two numbers
  }
}

/** Runs worth splitting: after an article ("a sixteen dollar glass"), at a connector, or at an ordinal. */
const SPLITTABLE = compile(String.raw`^an?\s|\band\b|\b(?:${Object.keys(ORDINALS).join("|")})\b`, { ignoreCase: true });
/** Tokens in the longest number phrase worth reading, which keeps splitting a run linear. */
const LONGEST_NUMBER_PHRASE = 12;

function* numberWordRuns(text: string, start: number, end: number): Generator<Fact> {
  const tokens = [...text.slice(start, end).matchAll(/[A-Za-z]+/g)].map((t) => [start + t.index!, start + t.index! + t[0].length]);
  let i = 0;
  while (i < tokens.length) {
    if (text.slice(tokens[i][0], tokens[i][1]).toLowerCase() === "and") { i++; continue; }
    let best: [number, bigint, string] | null = null;
    for (let j = Math.min(tokens.length, i + LONGEST_NUMBER_PHRASE) - 1; j >= i; j--) {
      const phrase = text.slice(tokens[i][0], tokens[j][1]);
      const value = wordsToNumber(phrase);
      if (value !== null && !phrase.toLowerCase().endsWith(" and")) { best = [j, value, phrase]; break; }
    }
    if (best === null) { i++; continue; }
    const [j, value, phrase] = best;
    const d = dec(value.toString());
    yield fact("quantity", tokens[i][0], tokens[j][1], phrase, d, [d]);
    i = j + 1;
  }
}

const LETTER = /\p{L}/u;

/** Spelled-out numbers below ten are Evidence but never Claims: mostly derived counts or idiom. */
function isSmallWordCount(f: Fact): boolean {
  return f.kind === "quantity" && LETTER.test(f.text[0] ?? "") && lessThan(f.value as Dec, 10);
}

// ------------------------------------------------------- Bahasa Melayu / Indonesia words

const MS_UNITS: Record<string, number> = {
  satu: 1, dua: 2, tiga: 3, empat: 4, lima: 5, enam: 6, tujuh: 7, lapan: 8, delapan: 8, sembilan: 9,
};
const MS_SE: Record<string, number> = { sepuluh: 10, sebelas: 11, seratus: 100, seribu: 1000, sejuta: 1e6 };
const MS_MULTIPLIERS: Record<string, number | null> = { belas: null, puluh: 10, ratus: 100 };
const MS_WORD = alternation([...Object.keys(MS_UNITS), ...Object.keys(MS_SE), ...Object.keys(MS_MULTIPLIERS), ...Object.keys(MALAY_MAGNITUDES)]);
const MS_NUMBER_WORDS = compile(String.raw`(?:${MS_WORD})(?:\s+(?:${MS_WORD}))*\b`, { ignoreCase: true });
const MS_KEYWORDS = new Set([...Object.keys(MS_UNITS), ...Object.keys(MS_SE)]);

/** "dua ratus lima puluh" → 250n, "sepuluh ribu" → 10000n. */
export function malayWordsToNumber(phrase: string): bigint | null {
  let total = 0n;
  let current = 0n;
  let pending: bigint | null = null;
  for (const w of phrase.toLowerCase().split(/\s+/).filter(Boolean)) {
    if (w in MS_UNITS) {
      if (pending !== null) return null;
      pending = BigInt(MS_UNITS[w]);
    } else if (w in MS_SE) {
      const value = BigInt(MS_SE[w]);
      if (value >= 1000n) {
        total += (current + (pending ?? 0n) || 1n) * value;
        current = 0n;
        pending = null;
      } else {
        current += value;
      }
    } else if (w === "belas") {
      current += (pending || 1n) + 10n;
      pending = null;
    } else if (w in MS_MULTIPLIERS) {
      current += (pending || 1n) * BigInt(MS_MULTIPLIERS[w] as number);
      pending = null;
    } else {
      total += (current + (pending ?? 0n) || 1n) * BigInt(MALAY_MAGNITUDES[w]);
      current = 0n;
      pending = null;
    }
  }
  return total + current + (pending ?? 0n);
}

function* malayNumberWords(text: string, ws: Words): Generator<Fact> {
  for (const m of anchored(MS_NUMBER_WORDS, text, ws, MS_KEYWORDS)) {
    const value = malayWordsToNumber(m[0]);
    if (value) {
      const d = dec(value.toString());
      yield fact("quantity", ...span(m), m[0], d, [d]);
    }
  }
}

// ------------------------------------------------------------------------ 中文 numerals

const CJK_DIGITS: Record<string, number> = {
  "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
};
const CJK_UNITS: Record<string, number> = { "十": 10, "百": 100, "千": 1000 };
const CJK_BIG: Record<string, number> = { "万": 1e4, "亿": 1e8 };
const CJK_CHARS = [...Object.keys(CJK_DIGITS), ...Object.keys(CJK_UNITS), ...Object.keys(CJK_BIG)].join("");
const CJK_NUMBER = String.raw`(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s?[${Object.keys(CJK_UNITS).join("")}${Object.keys(CJK_BIG).join("")}]*(?![克米瓦卡])` +
  String.raw`|[${CJK_CHARS}]+(?:点[${Object.keys(CJK_DIGITS).join("")}]+[万亿]*(?![十分刻]))?`;
const CJK_NUMERAL = compile(String.raw`(?<![第${CJK_CHARS}\d.,])(${CJK_NUMBER})`);
/**
 * 八块五 and 八元五角 are 8.50, 十块五毛五 is 10.55: after 块 or 元 a lone digit counts tenths (毛, 角) and the
 * next hundredths (分), but only where no other word starts (三块五花肉 is three pieces of pork belly).
 */
const CJK_MONEY = compile(String.raw`(?<![\d.,])(${CJK_NUMBER})\s?(${alternation(Object.keys(CJK_CURRENCIES))})(?:(?<=[块元])([1-9一二两三四五六七八九])(?![0-9十百千万〇零一二两三四五六七八九])(?=[毛角钱]|[^一-鿿]|$)(?:[毛角](?:([1-9一二两三四五六七八九])(?![0-9十百千万〇零一二两三四五六七八九])(?=[分钱]|[^一-鿿]|$)分?)?)?)?`);
const CJK_PERCENT = compile(String.raw`百分之(${CJK_NUMBER})`);
const CJK_CLOCK_NUMBER = String.raw`(?:[${Object.keys(CJK_DIGITS).join("")}十]{1,3}|[0-9]{1,2})`;
/** 十一点五十分 (11:50), 三点半 (3:30), 八点一刻 (8:15). 点 is o'clock here, not a decimal point. */
const CJK_CLOCK = compile(String.raw`(?<![${CJK_CHARS}0-9])(${CJK_CLOCK_NUMBER})点(?:(半)|(${CJK_CLOCK_NUMBER})分|([一三])刻)`);
const CJK_PM = new Set(["中午", "下午", "傍晚", "晚上"]);
/** 上午9点 (9:00), 下午3点半 (15:30), 晚上8点 (20:00): with a day part, the hour alone is a time. */
const CJK_DAYPART_CLOCK = compile(
  String.raw`(上午|早上|凌晨|中午|下午|傍晚|晚上)\s?(${CJK_CLOCK_NUMBER})点(?:(半)|(${CJK_CLOCK_NUMBER})分|([一三])刻|钟)?`,
);
const CJK_IDIOMS = ["十分", "万一", "千万", "一起", "一些", "一般", "一样", "一直", "一定", "一下", "一点", "一切", "统一", "唯一"];

/** "三千五百" → 3500, "1.2万" → 12000, "两百零五" → 205. */
export function cjkNumber(token: string): Dec {
  const lead = /^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?/.exec(token);
  if (lead) {
    let value = dec(lead[0]);
    for (const ch of token.slice(lead[0].length).trim()) value = mul(value, BigInt(CJK_UNITS[ch] ?? CJK_BIG[ch]));
    return value;
  }
  if (token.includes("点")) { // 一点五亿 = 1.5 × 10^8
    const at = token.indexOf("点");
    const rest = token.slice(at + 1);
    let fraction = "";
    for (const ch of rest) {
      if (!(ch in CJK_DIGITS)) break;
      fraction += String(CJK_DIGITS[ch]);
    }
    let value = add(cjkNumber(token.slice(0, at)), `0.${fraction}`);
    for (const ch of rest.slice(fraction.length)) value = mul(value, BigInt(CJK_BIG[ch]));
    return value;
  }
  let total = 0n;
  let section = 0n;
  let number = 0n;
  for (const ch of token) {
    if (ch in CJK_DIGITS) {
      number = BigInt(CJK_DIGITS[ch]);
    } else if (ch in CJK_UNITS) {
      section += (number || 1n) * BigInt(CJK_UNITS[ch]);
      number = 0n;
    } else if (ch === "万") {
      total += ((section + number) || 1n) * 10000n;
      section = 0n;
      number = 0n;
    } else { // 亿 scales everything before it, so 一万亿 is 10^12
      total = ((total + section + number) || 1n) * 100000000n;
      section = 0n;
      number = 0n;
    }
  }
  const chars = [...token];
  if (number && chars.length > 1 && chars[chars.length - 2] in SHORTHAND) number *= SHORTHAND[chars[chars.length - 2]]; // 一万五 is 15000
  return dec((total + section + number).toString());
}

/** A lone last digit after 百, 千 or 万 counts the next unit down; after 零 (一万零五) it is ones. */
const SHORTHAND: Record<string, bigint> = { 百: 10n, 千: 100n, 万: 1000n };

const CJK_ANY = new RegExp(`[${CJK_CHARS}]`);

function* cjkNumbers(text: string): Generator<Fact> {
  if (!CJK_ANY.test(text)) return;
  const numeral = (ch: string | undefined) => ch !== undefined && (CJK_CHARS.includes(ch) || /[0-9]/.test(ch));
  for (const idiom of CJK_IDIOMS) {
    let at = text.indexOf(idiom);
    while (at !== -1) {
      // 十分 alone is "very"; 三十分钟 is 30 minutes
      if (!numeral(text[at - 1]) && !numeral(text[at + idiom.length])) yield fact(EXEMPT, at, at + idiom.length, idiom, "");
      at = text.indexOf(idiom, at + 1);
    }
  }
  for (const m of CJK_NUMERAL.all(text)) {
    if (![...m[0]].some((ch) => CJK_CHARS.includes(ch))) continue;
    const value = cjkNumber(m[0]);
    yield fact("quantity", ...span(m), m[0], value, [value]);
  }
}

// ---------------------------------------------------------------------------- extract

const RECOGNISERS: Recogniser[] = [
  emails, urls, isoDatetimes, dates, lastDigits, phones, money, percents, temperatures, times, identifiers, cjkNumbers,
  fractions, quantities, numberWords, malayNumberWords,
];
/** Sources read a few forms more generously than Outputs do (ADR-0003): "May 19 and 20", uncued codes. */
const SOURCE_RECOGNISERS: Recogniser[] = RECOGNISERS.map((r) =>
  r === (dates as Recogniser) ? (sourceDates as Recogniser) : r === (identifiers as Recogniser) ? (sourceIdentifiers as Recogniser) : r
);

const ESCAPE = /\\(?:\\|x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|[nrtbf])/g;

const ONE_FOR_ONE = new Map<number, string>([
  ...[0x00a0, 0x2007, 0x2009, 0x200a, 0x202f, 0x205f, 0x3000, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006].map((cp) => [cp, " "] as [number, string]),
  ...[0xff10, 0x0660, 0x06f0, 0x0966].flatMap((base) => Array.from({ length: 10 }, (_, i) => [base + i, String(i)] as [number, string])),
  ...Array.from({ length: 26 }, (_, i) => [0xff21 + i, String.fromCharCode(0x41 + i)] as [number, string]),
  ...Array.from({ length: 26 }, (_, i) => [0xff41 + i, String.fromCharCode(0x61 + i)] as [number, string]),
  [0xff05, "%"], [0xff1a, ":"], [0xff04, "$"], [0xff0b, "+"], [0xff0d, "-"], [0xff0e, "."], [0x2212, "-"],
]);
const ONE_FOR_ONE_RE = new RegExp(`[${[...ONE_FOR_ONE.keys()].map((cp) => `\\u${cp.toString(16).padStart(4, "0")}`).join("")}]`, "g");

/**
 * Normalise the text recognisers scan, keeping every offset: blank escape sequences written
 * as text, turn Unicode spaces into spaces and full-width or other-script digits into ASCII.
 */
/** A token mixing letters and digits: COVID-19, CD8, IL-4, H1N1, 13G, 4WD (ADR-0008). */
const NAME = compile(String.raw`(?<![\w.-])(?=[\w-]*[A-Za-z])(?=[\w-]*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*(?![\w-]|\.\d)`);
/** An amount written against its currency code ("RMB105") is money, not a name. */
const CURRENCY_CODE = compile(String.raw`(?:rm|rmb|usd|us|sgd|eur|gbp|jpy|cny|inr|idr|thb|php|vnd|aud|cad|hkd|nzd|rp|rs)\d`, { ignoreCase: true });

/** Every name in `text` as [start, end, surface, Value], scanned as extract() scans (ADR-0008). */
export function names(text: string): [number, number, string, string][] {
  const scan = maskEscapes(text);
  return NAME.all(scan).filter((m) => CURRENCY_CODE.at(m[0], 0) === null)
    .map((m) => { const [a, b] = span(m); return [a, b, text.slice(a, b), nameValue(m[0])]; });
}

/**
 * A name's Value: lower case, without a hyphen between a letter and a digit ("COVID-19" and
 * "covid19" are one name; "X1-2" and "X12" are not).
 */
export function nameValue(token: string): string {
  return token.toLowerCase().replace(/(?<=[a-z])-(?=[0-9])|(?<=[0-9])-(?=[a-z])/g, "");
}

/** A name's shape: its Value with every run of digits as "#" ("covid#", "h#n#"). */
export function nameShape(value: string): string {
  return value.replace(/[0-9]+/g, "#");
}

function maskEscapes(text: string): string {
  let scan = text.replace(ONE_FOR_ONE_RE, (ch) => ONE_FOR_ONE.get(ch.charCodeAt(0))!);
  if (scan.includes("\\")) scan = scan.replace(ESCAPE, (m) => " ".repeat(m.length));
  if (scan.includes("·")) scan = scan.replace(/(?<=[0-9])·(?=[0-9])/g, "."); // "37·8": the Lancet's decimal point
  return scan;
}

const TWENTY_FOUR_HOUR = compile(String.raw`(?<![\w.,:])(?:1[3-9]|2[0-3]):(?:\d{2}|0(?!\d))(?!\s?[ap]\.?\s?m\b)`, { ignoreCase: true });

/** A text that writes any 13:00-23:59 time is on the 24-hour clock, so its bare "9:00" is 09:00. */
function readClockStyle(text: string, facts: Fact[]): Fact[] {
  if (!facts.some((f) => f.as24Hour) || !TWENTY_FOUR_HOUR.search(text)) return facts;
  return facts.map((f) => (f.as24Hour ? { ...f, value: f.as24Hour } : f));
}

/** Hard facts in `text`. With `claims`, Exempt spans and small spelled-out counts are skipped. */
export function extract(text: string, claims = false): Fact[] {
  const scan = maskEscapes(text);
  const taken = new Uint8Array(text.length);
  const ws = words(scan);
  let facts: Fact[] = [];
  for (const recognise of claims ? [exempt as Recogniser, ...RECOGNISERS] : SOURCE_RECOGNISERS) {
    for (let f of recognise(scan, ws)) {
      if (scan !== text) f = { ...f, text: text.slice(f.start, f.end) };
      if (taken.subarray(f.start, f.end).some(Boolean)) continue;
      taken.fill(1, f.start, f.end);
      facts.push(f);
    }
  }
  facts = facts.filter((f) => f.kind !== EXEMPT && !(claims && isSmallWordCount(f)));
  facts.sort((a, b) => a.start - b.start);
  return readClockStyle(scan, spelledAmounts(scan, text, facts));
}

const MAJOR_UNIT = compile(String.raw`\s+(${alternation(Object.keys(SUFFIX_CURRENCIES))})\b`, { ignoreCase: true });
const MINOR_JOIN = compile(String.raw`\s+(?:(?:and|dan)\s+)?`, { ignoreCase: true });
const MINOR_UNIT = compile(String.raw`\s+(?:cents?|sen)\b`, { ignoreCase: true });
/** A minor unit on its own is a hundredth: "50 sen" is RM0.50, "50 cents" and "50¢" are $0.50. */
const MINOR_ALONE = compile(String.raw`\s*(¢)|(?:\s+|-)(cents?|sen)\b`, { ignoreCase: true });

/**
 * "one hundred forty-nine dollars and ninety cents", "RM149 dan 90 sen": one amount, as a voice
 * agent writes it for text-to-speech. A number followed by a currency word is an amount, and
 * "[and|dan] N cents/sen" (N under 100) adds its minor unit.
 */
/** d / 100, exactly: "50" → "0.5", "2.5" → "0.025". */
function divideBy100(d: Dec): Dec {
  const negative = d.startsWith("-");
  const [whole, frac = ""] = (negative ? d.slice(1) : d).split(".");
  const padded = whole.padStart(3, "0");
  return dec(`${negative ? "-" : ""}${padded.slice(0, -2)}.${padded.slice(-2)}${frac}`);
}

function spelledAmounts(scan: string, text: string, facts: Fact[]): Fact[] {
  const out: Fact[] = [];
  for (let i = 0; i < facts.length; i++) {
    const f = facts[i];
    let currency: string | null = null;
    let major: Dec | null = null;
    let end = f.end;
    if (f.kind === "quantity") {
      const unit = MAJOR_UNIT.at(scan, f.end);
      if (unit) [currency, major, end] = [SUFFIX_CURRENCIES[unit[1].toLowerCase()], f.value as Dec, span(unit)[1]];
    } else if (f.kind === "money") {
      [currency, major] = f.value as [string, Dec];
    }
    if (currency === null || major === null) {
      const alone = f.kind === "quantity" ? MINOR_ALONE.at(scan, f.end) : null;
      if (alone) {
        const amount = divideBy100(f.value as Dec);
        const unit = (alone[2] ?? "").toLowerCase() === "sen" ? "MYR" : "$";
        const stop = span(alone)[1];
        out.push(fact("money", f.start, stop, text.slice(f.start, stop), [unit, amount], [amount, f.value as Dec]));
      } else out.push(f);
      continue;
    }
    const next = facts[i + 1];
    const join = MINOR_JOIN.at(scan, end);
    const minorUnit = next ? MINOR_UNIT.at(scan, next.end) : null;
    const minor = next?.value as Dec;
    if (join && next && next.kind === "quantity" && next.start === span(join)[1] && minorUnit
      && /^\d{1,2}$/.test(minor)) {
      const amount = add(major, dec(`0.${minor.padStart(2, "0")}`));
      const stop = span(minorUnit)[1];
      out.push(fact("money", f.start, stop, text.slice(f.start, stop), [currency, amount], [amount, major]));
      i++;
      continue;
    }
    out.push(f.kind === "money" ? f : fact("money", f.start, end, text.slice(f.start, end), [currency, major], [major]));
  }
  return out;
}
