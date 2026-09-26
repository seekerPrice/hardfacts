/**
 * hardfacts: deterministic provenance for the numbers, dates, money and IDs your LLM writes.
 *
 * TypeScript port of the Python reference implementation. Same Claims, same verdicts,
 * checked against a shared fixture of the Python test suite.
 */

import { add, compare, type Dec, dec, mul, sub } from "./decimal.ts";
import { CODES, codePointsBefore, currency, DOLLAR_FAMILY, extract, PREFIX_CURRENCIES, SUFFIX_CURRENCIES, type Fact, nameShape, names, type Value, YEN_FAMILY } from "./extract.ts";
import { compile } from "./regex.ts";

export type { Value } from "./extract.ts";

export const KIND_NAMES: Record<string, string> = {
  quantity: "number",
  percent: "percentage",
  money: "amount",
  temperature: "temperature",
  date: "date",
  time: "time",
  phone: "phone number",
  email: "email address",
  url: "link",
  identifier: "ID or code",
  name: "name with a number",
};
export const KINDS: ReadonlySet<string> = new Set(Object.keys(KIND_NAMES));

/** A Hard fact in a Source that supports a Claim. `span` indexes into `report.sources[source]`. */
export interface Evidence {
  source: number;
  span: [number, number];
  text: string;
}

/** Arithmetic over the Output's own Supported values that gives an Unsupported Claim's Value (ADR-0007). */
export interface Derivation {
  /** The operands as written, joined by −, + or ×: "$101.12 − $94.80". */
  expression: string;
  /** The operands' spans in the Output. */
  operands: [number, number][];
}

/** A Hard fact found in the Output, with its verdict. */
export interface Claim {
  kind: string;
  text: string;
  span: [number, number];
  value: Value;
  supported: boolean;
  evidence: Evidence[];
  /** For an Unsupported number, amount or percentage: how the Output's own values give it, if they do. */
  derivation: Derivation | null;
}

/** The result of one check. */
export interface Report {
  claims: Claim[];
  /** The text each Source was searched as; Evidence spans index into these. */
  sources: string[];
  unsupported: Claim[];
  /**
   * Unsupported Claims with no Derivation: values neither a Source nor the Output's own arithmetic accounts for.
   * A retry loop for a bot that must calculate (totals, price differences) can stop when this is empty.
   */
  unexplained: Claim[];
  ok: boolean;
}

// ---------------------------------------------------------------------------- matching

function sameCurrency(a: string | null, b: string | null): boolean {
  if (a === b || a === null || b === null) return true; // 元/块 name no particular currency
  return ([["$", DOLLAR_FAMILY], ["¥", YEN_FAMILY]] as const).some(
    ([generic, family]) => (a === generic || b === generic) && family.has(a) && family.has(b),
  );
}

function dateMatches(claim: string, evidence: string): boolean {
  return [...claim].every((c, i) => c === "X" || c === evidence[i]);
}

function phoneMatches(claim: string, evidence: string): boolean {
  const a = claim.replace(/^0+/, "");
  const b = evidence.replace(/^0+/, "");
  if (b.length >= a.length) return a.length >= 7 && b.endsWith(a);
  return b.length >= 9 && a.endsWith(b); // the Claim added a country code to a full national number
}

function urlMatches(claim: string, evidence: string): boolean {
  return evidence === claim || (evidence.startsWith(claim) && "/?#".includes(evidence[claim.length] ?? "\0"));
}

/** The digit string of a Fact that could be a phone number stored another way. */
/** Digits a quantity may have to be read as a digit string (phone, account); no phone number has more. */
const LONGEST_DIGITS = 20;

function digitsOf(f: Fact): string | null {
  if (f.kind === "phone") return f.value as string;
  if (f.kind === "identifier" && /^\d+$/.test(f.value as string)) return f.value as string;
  // no phone or account number is longer (Python reads at most 20 digits: str(int()) refuses huge ones)
  if (f.kind === "quantity" && !(f.value as Dec).includes(".") && (f.value as Dec).length <= LONGEST_DIGITS) return f.value as Dec;
  return null;
}

/** A git commit hash, as git writes it (lowercase, with a letter): its short and full forms name one commit. */
const GIT_HASH = /^(?=[0-9]*[a-f])[0-9a-f]{7,40}$/;
/** The ID of a resource in its URL (".../pull/3337", "/orders/48213"); not an image size or a page number. */
const PATH_NUMBER =
  /\/(?:pull|pulls|issues?|merge_requests|orders?|tickets?|invoices?|cases?|runs|jobs|builds|deployments?|reservations?|bookings?|shipments?)\/([0-9]{1,20})(?=[/?#]|$)/gi;
/** A Source hash long enough to be shortened: git's full hash, not an 8-character order code. */
const LONG_HASH = 12;
const isLongHash = (text: string): boolean => text.length >= LONG_HASH && GIT_HASH.test(text);
const pathNumbers = (url: string): string[] => [...url.matchAll(PATH_NUMBER)].map((m) => m[1]);

/** The digits a Fact's value ends with: 1591784 for gift_card_1591784, all of a phone number. */
function trailingDigits(f: Fact): string | null {
  if (f.kind === "identifier") return /[0-9]+$/.exec(f.value as string)?.[0] ?? null;
  return digitsOf(f);
}

/**
 * Evidence that states `amount` as a bare number: a quantity, or an all-digit ID ("2500000000").
 * A segment of a mixed ID (credit_card_7574394) is a stated number but never an amount.
 */
function plain(evidence: Fact, amount: Dec): boolean {
  if (evidence.kind === "quantity") return evidence.value === amount;
  return evidence.kind === "identifier" && /^\d+$/.test(evidence.value as string) && evidence.numbers.has(amount);
}

/** Digits a last-digit reference needs to match the end of a long bare number (not an ID or phone). */
const SUFFIX_DIGITS = 4;
/** Digits a bare quantity needs before it can be an account number whose end a reference names. */
const ACCOUNT_DIGITS = 7;

/**
 * "Ending in 1784": an ID or phone ending so, or a number that is those digits or a long account
 * number ending in them. Never a price or a count that happens to end in them ("1500", "12024").
 */
function endsWith(evidence: Fact, suffix: string): boolean {
  const digits = trailingDigits(evidence);
  if (digits === null || !digits.endsWith(suffix)) return false;
  if (evidence.kind === "identifier" || evidence.kind === "phone" || digits === suffix) return true;
  return digits.length >= ACCOUNT_DIGITS && suffix.length >= SUFFIX_DIGITS;
}

/** Does this Evidence support this Claim? (ADR-0003: doubt resolves to Supported.) */
function supports(evidence: Fact, claim: Fact): boolean {
  if (claim.kind === "phone" || (evidence.kind === "phone" && (claim.kind === "identifier" || claim.kind === "quantity"))) {
    // "+60123456789", wa_id "60123456789" and {"phone": 60123456789} are one number
    const [a, b] = [digitsOf(claim), digitsOf(evidence)];
    if (a && b && phoneMatches(a, b)) return true;
    if (claim.kind === "phone") return false;
  }
  switch (claim.kind) {
    case "quantity":
      return evidence.numbers.has(claim.value as Dec);
    case "money": {
      const [currency, value] = claim.value as [string | null, Dec];
      if (evidence.kind === "money") {
        const [eCurrency, eValue] = evidence.value as [string | null, Dec];
        return eValue === value && sameCurrency(currency, eCurrency);
      }
      return plain(evidence, value);
    }
    case "percent":
      return (evidence.kind === "percent" && evidence.value === claim.value) || plain(evidence, claim.value as Dec);
    case "temperature": {
      const [value, unit] = claim.value as [Dec, string];
      if (evidence.kind === "temperature") {
        const [eValue, eUnit] = evidence.value as [Dec, string];
        return eValue === value && eUnit === unit; // a conversion is a derived value (ADR-0005)
      }
      return plain(evidence, value);
    }
    case "date":
      return evidence.kind === "date" &&
        (claim.value as string[]).some((c) => (evidence.value as string[]).some((e) => dateMatches(c, e)));
    case "identifier":
      if ((claim.value as string).startsWith("*")) return endsWith(evidence, (claim.value as string).slice(1));
      if (/^\d+$/.test(claim.value as string)) {
        if (evidence.kind === "identifier") return evidence.value === claim.value; // codes are strings: "00123" is not "123"
        // ".../pull/3337" states PR #3337, not 3337 lines
        if (evidence.kind === "url") return pathNumbers(evidence.value as string).includes(claim.value as string);
        return evidence.numbers.has(dec(claim.value as string)); // "#48213" and 48213, "1500000000" and "$1.5 billion"
      }
      if (evidence.kind === "identifier" && GIT_HASH.test(claim.text) && isLongHash(evidence.text)) {
        return (evidence.value as string).startsWith(claim.value as string); // "33e41b9" from 33e41b9670c2…; never longer
      }
      return evidence.kind === "identifier" && evidence.value === claim.value;
    case "email":
      return evidence.kind === claim.kind && evidence.value === claim.value;
    case "url":
      if (evidence.kind === "email") {
        const e = evidence.value as string;
        return urlMatches(claim.value as string, e.slice(e.lastIndexOf("@") + 1));
      }
      return evidence.kind === "url" && urlMatches(claim.value as string, evidence.value as string);
    case "time":
      return evidence.kind === "time" && (claim.value as string[]).some((r) => (evidence.value as string[]).includes(r));
    default:
      return false;
  }
}

// -------------------------------------------------------------------------- derivations

const ARITHMETIC_KINDS = new Set(["quantity", "money", "percent"]);
/**
 * Candidates the search may examine per check (one unit per operand tried, in a fixed order both ports
 * share). Past it, the remaining values get no Derivation: they stay Unsupported, and unexplained.
 */
const WORK_PER_CHECK = 200_000;
const LARGEST_MULTIPLIER = 9;
/** Operands for which sums of 4 and 5 are tried: C(16, 5) = 4,368 sums per flagged value. */
const SUMS_OF_FOUR_OR_FIVE_UP_TO = 16;
/** Operands for which sums of 3 are tried: C(60, 3) = 34,220 sums per flagged value. */
const SUMS_OF_THREE_UP_TO = 60;

class OutOfBudget extends Error {}

class Budget {
  left: number;
  constructor(units: number) {
    this.left = units;
  }
  spend(): void {
    this.left -= 1;
    if (this.left < 0) throw new OutOfBudget();
  }
}

function claimAmount(c: Claim): Dec {
  return c.kind === "money" ? (c.value as string[])[1] : (c.value as Dec);
}

/**
 * The lexicographically first `k` indices from `start` on whose operands sum to `goal`: the same
 * answer as scanning every k-combination in order, but the last operand is a lookup, and a branch
 * stops once its smallest possible sum overshoots or its largest falls short (operands are
 * positive and ascending).
 */
function firstSum(operands: Dec[], index: Map<Dec, number>, k: number, goal: Dec, budget: Budget, start = 0): number[] | null {
  if (k === 1) {
    const i = index.get(goal);
    return i !== undefined && i >= start ? [i] : null;
  }
  const largest = operands.slice(Math.max(start, operands.length - k)).reduce(add, "0");
  if (operands.length - start < k || compare(largest, goal) < 0) return null; // even the k largest fall short
  for (let i = start; i < operands.length; i++) {
    budget.spend();
    if (compare(mul(operands[i], BigInt(k)), goal) > 0) return null;
    const rest = firstSum(operands, index, k - 1, sub(goal, operands[i]), budget, i + 1);
    if (rest !== null) return [i, ...rest];
  }
  return null;
}

/** The Output's Supported values, grouped once per Kind and currency, and one work budget. */
class Search {
  private readonly claims: Claim[];
  private readonly budget = new Budget(WORK_PER_CHECK);
  private readonly groups = new Map<string, [Dec[], Map<Dec, Claim>]>();
  private readonly multipliers = new Map<Dec, Claim>();

  constructor(claims: Claim[]) {
    this.claims = claims;
    for (const c of claims) {
      const v = c.value as Dec;
      if (c.supported && c.kind === "quantity" && !v.includes(".") && compare(v, "2") >= 0 && compare(v, String(LARGEST_MULTIPLIER)) <= 0 &&
        !this.multipliers.has(v)) this.multipliers.set(v, c);
    }
  }

  private operands(target: Claim): [Dec[], Map<Dec, Claim>] {
    const currency = target.kind === "money" ? (target.value as string[])[0] : null;
    const key = `${target.kind}\u0000${currency}`;
    let group = this.groups.get(key);
    if (!group) {
      const first = new Map<Dec, Claim>();
      for (const c of this.claims) {
        const a = claimAmount(c);
        const currencyOk = c.kind !== "money" || sameCurrency((c.value as string[])[0], currency); // never €100 − $40
        if (c.supported && c.kind === target.kind && compare(a, "0") > 0 && currencyOk && !first.has(a)) first.set(a, c);
      }
      group = [[...first.keys()].sort(compare), first];
      this.groups.set(key, group);
    }
    return group;
  }

  /** The first Derivation of `target` in the fixed order: differences, sums by size, products (ADR-0007). */
  derive(target: Claim): Derivation | null {
    if (!ARITHMETIC_KINDS.has(target.kind) || this.budget.left <= 0) return null;
    const goal = claimAmount(target);
    const [every, first] = this.operands(target);
    const operands = every.filter((x) => x !== goal);
    const made = (symbol: string, parts: Claim[]): Derivation => ({
      expression: parts.map((p) => p.text).join(` ${symbol} `),
      operands: parts.map((p) => [...p.span] as [number, number]),
    });
    try {
      const index = new Map(operands.map((x, i) => [x, i]));
      for (const a of operands) {
        this.budget.spend();
        const b = sub(a, goal);
        if (index.has(b) && b !== a) return made("−", [first.get(a)!, first.get(b)!]);
      }
      const largest = operands.length <= SUMS_OF_FOUR_OR_FIVE_UP_TO ? 5 : operands.length <= SUMS_OF_THREE_UP_TO ? 3 : 2;
      for (let k = 2; k <= largest; k++) {
        const picked = firstSum(operands, index, k, goal, this.budget);
        if (picked !== null) return made("+", picked.map((i) => first.get(operands[i])!));
      }
      for (const a of operands) {
        for (const m of [...this.multipliers.keys()].sort(compare)) {
          this.budget.spend();
          if (mul(a, BigInt(m)) === goal) return made("×", [first.get(a)!, this.multipliers.get(m)!]);
        }
      }
    } catch (e) {
      if (e instanceof OutOfBudget) return null;
      throw e;
    }
    return null;
  }
}

// ---------------------------------------------------------------------------- the index
// check() visits, for each Claim, only the Evidence that shares a key with it. The keys are derived
// from supports() rule by rule (the same derivation as _match.py), so supports(e, c) implies a shared
// key. bench/index_differential.py checks the Python index against the brute-force pairing, and the
// differentials check this port against Python.

function phoneKey(digits: string | null): string | null {
  const stripped = (digits ?? "").replace(/^0+/, "");
  return stripped.length >= 7 ? `p\u0000${stripped.slice(-7)}` : null;
}

function dateKeys(r: string): string[] {
  const [year, month, day] = [r.slice(0, 4), r.slice(5, 7), r.slice(8)];
  const keys = [`m\u0000${month}`];
  if (day !== "XX") keys.push(`md\u0000${month}\u0000${day}`);
  if (year !== "XXXX") keys.push(`ym\u0000${year}\u0000${month}`);
  if (day !== "XX" && year !== "XXXX") keys.push(`ymd\u0000${year}\u0000${month}\u0000${day}`);
  return keys;
}

function dateClaimKey(r: string): string {
  const [year, month, day] = [r.slice(0, 4), r.slice(5, 7), r.slice(8)];
  if (year !== "XXXX" && day !== "XX") return `ymd\u0000${year}\u0000${month}\u0000${day}`;
  if (day !== "XX") return `md\u0000${month}\u0000${day}`;
  if (year !== "XXXX") return `ym\u0000${year}\u0000${month}`;
  return `m\u0000${month}`;
}

const host = (url: string): string => url.split(/[/?#]/, 1)[0];

function evidenceKeys(e: Fact): Set<string> {
  const keys = new Set<string>([...e.numbers].map((x) => `n\u0000${x}`));
  const v = e.value;
  if (e.kind === "quantity" || e.kind === "percent") keys.add(`n\u0000${v}`);
  else if (e.kind === "money") keys.add(`n\u0000${(v as string[])[1]}`);
  else if (e.kind === "temperature") keys.add(`n\u0000${(v as string[])[0]}`);
  else if (e.kind === "date") for (const r of v as string[]) for (const k of dateKeys(r)) keys.add(k);
  else if (e.kind === "time") for (const r of v as string[]) keys.add(`t\u0000${r}`);
  else if (e.kind === "email") {
    keys.add(`i\u0000${v}`);
    keys.add(`h\u0000${(v as string).slice((v as string).lastIndexOf("@") + 1)}`);
  } else if (e.kind === "url") {
    keys.add(`h\u0000${host(v as string)}`);
    for (const n of pathNumbers(v as string)) keys.add(`u\u0000${n}`);
  } else if (e.kind === "identifier") {
    keys.add(`i\u0000${v}`);
    if (isLongHash(e.text)) keys.add(`g\u0000${(v as string).slice(0, 7)}`);
  }
  const phone = phoneKey(digitsOf(e));
  if (phone) keys.add(phone);
  const trailing = trailingDigits(e);
  if (trailing && trailing.length >= 3) { // endsWith: an ID or phone ending so, or a long account number
    if (e.kind === "identifier" || e.kind === "phone" || trailing.length >= ACCOUNT_DIGITS) keys.add(`s\u0000${trailing.slice(-3)}`);
    keys.add(`sx\u0000${trailing}`); // or the very digits ("last4": "4242")
  }
  return keys;
}

function claimKeys(c: Fact): string[] {
  const keys: string[] = [];
  const v = c.value;
  if (c.kind === "quantity" || c.kind === "percent") keys.push(`n\u0000${v}`);
  else if (c.kind === "money") keys.push(`n\u0000${(v as string[])[1]}`);
  else if (c.kind === "temperature") keys.push(`n\u0000${(v as string[])[0]}`);
  else if (c.kind === "date") for (const r of v as string[]) keys.push(dateClaimKey(r));
  else if (c.kind === "time") for (const r of v as string[]) keys.push(`t\u0000${r}`);
  else if (c.kind === "email") keys.push(`i\u0000${v}`);
  else if (c.kind === "url") keys.push(`h\u0000${host(v as string)}`);
  else if (c.kind === "identifier") {
    const s = v as string;
    if (s.startsWith("*")) keys.push(`s\u0000${s.slice(-3)}`, `sx\u0000${s.slice(1)}`);
    else if (/^\d+$/.test(s)) keys.push(`i\u0000${s}`, `n\u0000${dec(s)}`, `u\u0000${s}`);
    else {
      keys.push(`i\u0000${s}`);
      if (GIT_HASH.test(c.text)) keys.push(`g\u0000${s.slice(0, 7)}`);
    }
  }
  if (c.kind === "phone" || c.kind === "identifier" || c.kind === "quantity") {
    const phone = phoneKey(digitsOf(c));
    if (phone) keys.push(phone);
  }
  return keys;
}

// ------------------------------------------------------------------------------- check

/** Render a structured Source the way Python's json.dumps(ensure_ascii=False) does. */
export function render(source: unknown): string {
  if (typeof source === "string") return source;
  return dumps(source);
}

/** A JS number in plain decimal notation: 1e+21 → "1000000000000000000000", 5e-7 → "0.0000005". */
function plainNumber(n: number): string {
  if (Number.isNaN(n)) return "NaN";
  if (!Number.isFinite(n)) return n > 0 ? "Infinity" : "-Infinity";
  const s = String(n);
  const m = /^(-?)(\d+)(?:\.(\d+))?e([+-]\d+)$/.exec(s);
  if (!m) return s;
  const [, sign, whole, frac = "", exp] = m;
  const digits = whole + frac;
  const point = whole.length + Number(exp);
  if (point <= 0) return `${sign}0.${"0".repeat(-point)}${digits}`.replace(/0+$/, "");
  if (point >= digits.length) return sign + digits + "0".repeat(point - digits.length);
  return `${sign}${digits.slice(0, point)}.${digits.slice(point)}`;
}

/** JSON punctuation already rendered, waiting on the dumps stack. */
class Raw {
  readonly text: string;
  constructor(text: string) {
    this.text = text;
  }
}

/** Iterative, so a source nested thousands of levels deep renders instead of overflowing the stack. */
function dumps(value: unknown): string {
  const out: string[] = [];
  const stack: unknown[] = [value];
  while (stack.length) {
    const v = stack.pop();
    if (v instanceof Raw) {
      out.push(v.text);
    } else if (Array.isArray(v)) {
      stack.push(new Raw("]"));
      for (let i = v.length - 1; i >= 0; i--) {
        stack.push(v[i]);
        if (i) stack.push(new Raw(", "));
      }
      stack.push(new Raw("["));
    } else if (v !== null && typeof v === "object" && !(v instanceof Date)) {
      const entries = Object.entries(v as Record<string, unknown>);
      stack.push(new Raw("}"));
      for (let i = entries.length - 1; i >= 0; i--) {
        stack.push(entries[i][1]);
        stack.push(new Raw(`${i ? ", " : ""}${JSON.stringify(entries[i][0])}: `));
      }
      stack.push(new Raw("{"));
    } else {
      out.push(scalar(v));
    }
  }
  return out.join("");
}

function scalar(v: unknown): string {
  if (v === null || v === undefined) return "null";
  if (typeof v === "string" || typeof v === "boolean") return JSON.stringify(v);
  if (typeof v === "number") return plainNumber(v);
  if (typeof v === "bigint") return v.toString();
  if (v instanceof Date) return JSON.stringify(v.toISOString());
  return JSON.stringify(String(v));
}

/** What introduces the conversation's own date: "The current time is 2024-05-15", {"now": "2024-07-30"}. */
const ANCHOR = compile(
  String.raw`(?:\b(?:current[\s_-]*(?:time|date)|today(?:'s\s+date)?|it(?:'s|\s+is)\s+(?:currently|now)|right\s+now|(?:time|date)\s+now\s+is|now\W{0,3}:|as\s+(?:of|at)|hari\s+ini)` +
    String.raw`|今天|现在)[^\n\d]{0,25}$`,
  { ignoreCase: true },
);
/** More distinct anchor years than this and the conversation's year is ambiguous: no year is lent. */
const ANCHOR_YEARS = 2;

/**
 * A date a Source states without a year ("May 23rd", as a user types it) also reads with the
 * conversation's year: the year of a date introduced as the current time, today or now. Never
 * any year a Source happens to mention (a record's created_at, an unrelated event).
 */
function withYears(evidence: (readonly [number, Fact])[], rendered: string[]): (readonly [number, Fact])[] {
  const anchors = [...new Set(evidence.flatMap(([i, e]) =>
    e.kind === "date" && ANCHOR.search(codePointsBefore(rendered[i], e.start, 40)) !== null
      ? (e.value as string[]).filter((r) => r[0] !== "X").map((r) => r.slice(0, 10)) : []))].sort();
  if (!anchors.length || new Set(anchors.map((a) => a.slice(0, 4))).size > ANCHOR_YEARS) return evidence;
  return evidence.map(([i, e]) => {
    const readings = e.value as string[];
    if (e.kind !== "date" || !readings.some((r) => r.startsWith("XXXX"))) return [i, e] as const;
    const added = readings.filter((r) => r.startsWith("XXXX")).flatMap((r) => anchors.flatMap((a) => lentYears(r, a)));
    return [i, { ...e, value: [...new Set([...readings, ...added])] }] as const;
  });
}

/**
 * The anchor's year, and the next or previous one when that puts the date within half a year
 * (183 days) of the anchor: on 2025-12-30, "Jan 2" reads as 2 January 2026 as well as 2025 (an
 * order history's "Mar 5" is past; an ETA's "Jan 2" is next year; doubt keeps both). Never a date
 * that doesn't exist: "Feb 29" in 2027 reads as 2028, the nearest leap year.
 */
function lentYears(reading: string, anchor: string): string[] {
  const year = Number(anchor.slice(0, 4));
  const candidates = [year];
  if (anchor[5] !== "X" && reading[5] !== "X" && reading[8] !== "X") {
    const [month, day] = [Number(reading.slice(5, 7)), Number(reading.slice(8, 10))];
    const centre = ordinal(year, Number(anchor.slice(5, 7)), anchor[8] !== "X" ? Number(anchor.slice(8, 10)) : 15)!;
    for (const y of [year - 1, year + 1]) {
      const o = ordinal(y, month, day);
      if (o !== null && Math.abs(o - centre) <= 183) candidates.push(y);
    }
  }
  let valid = candidates.filter((y) => reading[8] === "X" || ordinal(y, Number(reading.slice(5, 7)), Number(reading.slice(8, 10))) !== null);
  if (!valid.length && reading.slice(5, 10) === "02-29") { // "Feb 29" means a leap year: the nearest one
    const leaps = [];
    for (let y = year - 3; y < year + 5; y++) if (ordinal(y, 2, 29) !== null) leaps.push(y);
    leaps.sort((a, b) => Math.abs(a - year) - Math.abs(b - year) || a - b);
    valid = [leaps[0]];
  }
  return valid.map((y) => String(y).padStart(4, "0") + reading.slice(4));
}

/** Days since the epoch, or null for a date that doesn't exist. */
function ordinal(year: number, month: number, day: number): number | null {
  const d = new Date(Date.UTC(year, month - 1, day));
  if (year < 100) d.setUTCFullYear(year);
  return d.getUTCFullYear() === year && d.getUTCMonth() === month - 1 && d.getUTCDate() === day ? d.getTime() / 86400000 : null;
}

/**
 * Evidence listed per Claim, first in Source order. A value that recurs thousands of times (a "5" in a table)
 * would otherwise make the Report itself quadratic; one piece of Evidence is enough to support a Claim.
 */
export const EVIDENCE_PER_CLAIM = 10;

export interface CheckOptions {
  /** Only check Claims of these Kinds, e.g. `["identifier", "phone", "money"]` for a support bot. */
  kinds?: Iterable<string>;
}

/**
 * Check every Hard fact in `output` against `sources`.
 *
 * Sources are strings or JSON-like values (tool results), searched as their JSON rendering.
 */
export function check(output: string, sources: unknown[], options: CheckOptions = {}): Report {
  const kinds = options.kinds === undefined ? null : new Set(options.kinds);
  if (kinds) {
    const unknown = [...kinds].filter((k) => !KINDS.has(k)).sort();
    if (unknown.length) throw new RangeError(`unknown kinds: ${unknown.join(", ")}; expected some of ${[...KINDS].sort().join(", ")}`);
  }
  if (!Array.isArray(sources)) {
    throw new TypeError("sources must be a list of strings or JSON-like values; wrap a single source in a list");
  }
  const rendered = sources.map(render);
  const evidence = withYears(rendered.flatMap((text, i) => extract(text).map((f) => [i, f] as const)), rendered);
  const index = new Map<string, number[]>();
  const moneyIndex = new Map<string, number[]>(); // money Evidence names its own currency
  evidence.forEach(([, e], position) => {
    for (const key of evidenceKeys(e)) {
      const list = index.get(key);
      if (list) list.push(position);
      else index.set(key, [position]);
      if (e.kind === "money") {
        const money = moneyIndex.get(key);
        if (money) money.push(position);
        else moneyIndex.set(key, [position]);
      }
    }
  });
  const named = sources.map(currenciesNamed);
  const ends = sourceEnds(evidence, rendered.length);
  const claims: Claim[] = [];
  const facts = extract(output, true);
  for (const f of facts) {
    if (kinds && !kinds.has(f.kind)) continue;
    const keys = claimKeys(f);
    const candidates = merged(keys.map((k) => index.get(k)).filter((l): l is number[] => l !== undefined));
    const found: Evidence[] = [];
    let money: number[] | null = null;
    for (let k = 0; k < candidates.length && found.length < EVIDENCE_PER_CLAIM;) {
      const p = candidates[k];
      const i = evidence[p][0];
      if (otherCurrency(f, i, named)) {
        // a bare number there is in another currency; its money Evidence still speaks for itself.
        // Take those, then skip the rest of that Source in one step.
        money ??= merged(keys.map((key) => moneyIndex.get(key)).filter((l): l is number[] => l !== undefined));
        const stop = lowerBound(candidates, ends[i], k);
        for (let q = lowerBound(money, p, 0); q < money.length && money[q] < ends[i]; q++) {
          const e = evidence[money[q]][1];
          if (!supports(e, f)) continue;
          found.push({ source: i, span: [e.start, e.end], text: e.text });
          if (found.length === EVIDENCE_PER_CLAIM) break;
        }
        k = stop;
        continue;
      }
      k++;
      if (!supports(evidence[p][1], f)) continue;
      found.push({ source: i, span: [evidence[p][1].start, evidence[p][1].end], text: evidence[p][1].text });
    }
    claims.push({ kind: f.kind, text: f.text, span: [f.start, f.end], value: f.value, supported: found.length > 0, evidence: found, derivation: null });
  }
  if (!kinds || kinds.has("name")) {
    claims.push(...nameClaims(output, rendered, facts.map((f) => [f.start, f.end] as [number, number])));
    claims.sort((x, y) => x.span[0] - y.span[0]);
  }
  const search = new Search(claims);
  for (const c of claims) if (!c.supported && ARITHMETIC_KINDS.has(c.kind)) c.derivation = search.derive(c);
  const unsupported = claims.filter((c) => !c.supported);
  const unexplained = unsupported.filter((c) => c.derivation === null);
  return { claims, sources: rendered, unsupported, unexplained, ok: unsupported.length === 0 };
}

const KNOWN = new Set([...CODES, "CNY", ...Object.values(PREFIX_CURRENCIES), ...Object.values(SUFFIX_CURRENCIES)]);
/** The whitespace both ports strip from a currency value. */
const SPACE = /^[ \t\n\r\f\v]+|[ \t\n\r\f\v]+$/g;
const KEY_WORD = /[A-Z]?[a-z]+|[A-Z]+(?![a-z])|[0-9]+/g;

/** "currency", "currency_code", "currencyCode", "ccy_code", "cur"; not "recurring" or "current". */
function isCurrencyKey(key: string): boolean {
  return (key.match(KEY_WORD) ?? []).some((w) => ["currency", "ccy", "cur", "curr"].includes(w.toLowerCase()));
}

/** A JSON object or array written as a string, or undefined. */
function parseJson(text: string): unknown {
  const t = text.replace(SPACE, "");
  if (!t || !"{[".includes(t[0])) return undefined;
  try {
    return JSON.parse(t);
  } catch {
    return undefined;
  }
}

/**
 * The currencies a JSON Source names in a currency key ("currency", "currency_code", "ccy"…):
 * {"amount": 50, "currency": "myr"} names MYR, also when the JSON arrives as a string, as tool
 * messages do. Free text and other amounts name nothing, so a note like "USD accepted" is no
 * reason to doubt an amount (ADR-0003).
 */
function currenciesNamed(source: unknown): Set<string> {
  const found = new Set<string>();
  const stack: unknown[] = [source];
  while (stack.length) {
    const node = stack.pop();
    if (typeof node === "string") {
      const parsed = parseJson(node);
      if (parsed !== undefined) stack.push(parsed);
    } else if (Array.isArray(node)) {
      for (const x of node) stack.push(x);
    } else if (node !== null && typeof node === "object") {
      for (const [key, value] of Object.entries(node)) {
        if (typeof value === "string" && isCurrencyKey(key)) {
          const code = currency(value.replace(SPACE, ""));
          if (KNOWN.has(code)) found.add(code); // "Malaysian Ringgit" is no code: doubt, not another currency
        } else stack.push(value);
      }
    }
  }
  return found;
}

/** For each Source, the position just past its last piece of Evidence (Evidence is in Source order). */
function sourceEnds(evidence: readonly (readonly [number, Fact])[], count: number): number[] {
  const ends = new Array<number>(count).fill(0);
  evidence.forEach(([i], position) => { ends[i] = position + 1; });
  return ends;
}

/** Every position in the sorted lists, once, ascending. */
function merged(lists: number[][]): number[] {
  return lists.length === 1 ? lists[0] : [...new Set(lists.flat())].sort((x, y) => x - y);
}

/** The first index in sorted `list`, at or after `from`, whose value is at least `value`. */
function lowerBound(list: number[], value: number, from: number): number {
  let [lo, hi] = [from, list.length];
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (list[mid] < value) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/**
 * A bare number is in the currency its Source names: {"amount": 50, "currency": "MYR"} doesn't
 * support "USD 50". Money Evidence is compared by supports() itself; a Source naming no currency,
 * or a compatible one, still supports (ADR-0003).
 */
function otherCurrency(claim: Fact, source: number, named: Set<string>[]): boolean {
  const code = (claim.value as [string | null, string])[0];
  if (claim.kind !== "money" || code === null || !named[source].size) return false;
  return ![...named[source]].some((c) => sameCurrency(code, c));
}

/** Names in the Output that a same-shaped name in the Sources makes checkable (ADR-0008). */
function nameClaims(output: string, rendered: string[], taken: [number, number][]): Claim[] {
  const byValue = new Map<string, Evidence[]>();
  rendered.forEach((text, i) => {
    for (const [start, end, surface, v] of names(text)) {
      const list = byValue.get(v) ?? [];
      list.push({ source: i, span: [start, end], text: surface });
      byValue.set(v, list);
    }
  });
  if (!byValue.size) return [];
  const shapes = new Set([...byValue.keys()].map(nameShape));
  const found: Claim[] = [];
  let t = 0; // taken spans are in order and don't overlap; so are names: one forward walk
  for (const [start, end, surface, value] of names(output)) {
    while (t < taken.length && taken[t][1] <= start) t++;
    if (!shapes.has(nameShape(value)) || (t < taken.length && taken[t][0] < end)) continue;
    const evidence = (byValue.get(value) ?? []).slice(0, EVIDENCE_PER_CLAIM);
    found.push({ kind: "name", text: surface, span: [start, end], value, supported: evidence.length > 0, evidence, derivation: null });
  }
  return found;
}

/** A correction instruction for the model that wrote the Output, or "" if nothing is Unsupported. */
export function feedback(report: Report): string {
  if (report.ok) return "";
  const lines = report.unsupported.map((c) =>
    c.derivation
      ? `- "${c.text}" (${KIND_NAMES[c.kind] ?? c.kind}, which you computed as ${c.derivation.expression}: check those are the right values to combine)`
      : `- "${c.text}" (${KIND_NAMES[c.kind] ?? c.kind})`
  );
  return (
    "Your draft states values that do not appear in the sources you were given:\n" +
    lines.join("\n") +
    "\n\nRewrite the draft using only values copied exactly from the sources. " +
    "If the sources don't contain a value, say so instead of supplying one. " +
    "Keep a value you calculated only if the calculation uses the right values, and show the calculation."
  );
}

/** The Report as plain JSON, in the same shape as the Python package's `Report.to_dict()`. */
export function toJSON(report: Report) {
  const plain = (c: Claim) => ({ kind: c.kind, text: c.text, span: c.span, value: c.value, derivation: c.derivation });
  return {
    ok: report.ok,
    unsupported: report.unsupported.map(plain),
    claims: report.claims.map((c) => ({ ...plain(c), supported: c.supported, evidence: c.evidence })),
    sources: report.sources,
  };
}
