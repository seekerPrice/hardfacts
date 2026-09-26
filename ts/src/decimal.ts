/**
 * Exact decimal Values as canonical strings: "1200", "2.1", "0.5".
 *
 * JavaScript numbers can't hold 2.1 billion and 0.1 exactly at once, and a Value
 * must compare equal only when it is the same number. A canonical string (no
 * exponent, no trailing zeros) is exact, hashable in a Set, and identical to what
 * the Python package serialises (`format(value.normalize(), "f")`).
 */

export type Dec = string;

function toParts(d: Dec): [bigint, number] {
  const negative = d.startsWith("-");
  const body = negative ? d.slice(1) : d;
  const [whole, frac = ""] = body.split(".");
  const n = BigInt((whole || "0") + frac);
  return [negative ? -n : n, frac.length];
}

function fromParts(n: bigint, scale: number): Dec {
  const negative = n < 0n;
  let digits = (negative ? -n : n).toString();
  if (scale > 0) {
    digits = digits.padStart(scale + 1, "0");
    let whole = digits.slice(0, -scale);
    let frac = digits.slice(-scale).replace(/0+$/, "");
    whole = whole.replace(/^0+(?=\d)/, "");
    digits = frac ? `${whole}.${frac}` : whole;
  }
  return negative && digits !== "0" ? `-${digits}` : digits;
}

/** Binary floating-point noise in a tool result: 302.67 - 298.91 prints as 3.759999999999991. */
const FLOAT_NOISE = /^(\d+)\.(\d*?)(0{6,}|9{6,})\d{0,3}$/;
const FLOAT_NOISE_DIGITS = 15;
/** Characters a rendered double can take; longer is no float, and the lazy noise pattern is quadratic. */
const LONGEST_FLOAT = 40;

/** "1,200.50" → "1200.5"; ".9" → "0.9"; "007" → "7"; "3.759999999999991" → "3.76". */
export function dec(text: string): Dec {
  // "1.500.000" and "1.234.567,89": dots group thousands and a comma marks decimals
  if ((text.match(/\./g) ?? []).length >= 2) {
    const [n, s] = toParts(text.replace(/\./g, "").replace(",", "."));
    return fromParts(n, s);
  }
  const clean = text.replace(/,/g, "");
  const noise = clean.length <= LONGEST_FLOAT ? FLOAT_NOISE.exec(clean) : null;
  // a double holds 15-17 significant digits, so noise lives there: "5.1000000000009" (14) is a real value
  if (noise && clean.replace(".", "").replace(/^0+/, "").length >= FLOAT_NOISE_DIGITS) {
    const [, whole, kept, run] = noise;
    const [n, s] = toParts(kept ? `${whole}.${kept}` : whole); // once: the kept digits are no float to round again
    const value = fromParts(n, s);
    return run[0] === "9" ? add(value, kept ? `0.${"0".repeat(kept.length - 1)}1` : "1") : value;
  }
  const [n, s] = toParts(clean.startsWith(".") ? `0${clean}` : clean);
  return fromParts(n, s);
}

export function mul(d: Dec, factor: number | bigint): Dec {
  const [n, s] = toParts(d);
  return fromParts(n * BigInt(factor), s);
}

export function add(a: Dec, b: Dec): Dec {
  const [na, sa] = toParts(a);
  const [nb, sb] = toParts(b);
  const s = Math.max(sa, sb);
  return fromParts(na * 10n ** BigInt(s - sa) + nb * 10n ** BigInt(s - sb), s);
}

export function sub(a: Dec, b: Dec): Dec {
  return add(a, b.startsWith("-") ? b.slice(1) : `-${b}`);
}

/** Negative, zero or positive as a is less than, equal to or greater than b. */
export function compare(a: Dec, b: Dec): number {
  const d = sub(a, b);
  return d === "0" ? 0 : d.startsWith("-") ? -1 : 1;
}

export function lessThan(a: Dec, b: number): boolean {
  const [n, s] = toParts(a);
  return n < BigInt(b) * 10n ** BigInt(s);
}
