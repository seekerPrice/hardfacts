/**
 * Python `re` patterns, compiled with Python's ASCII semantics.
 *
 * The Python package is the reference implementation, so patterns are copied
 * verbatim and translated here rather than rewritten by hand. JavaScript's `\w`,
 * `\d` and `\b` are already ASCII-only. `\s` is not (it also matches U+00A0 and
 * friends), so it becomes Python's ASCII whitespace class.
 */

const WS = " \\t\\n\\r\\f\\v";

const ASCII_LETTER = /[A-Za-z]/;

function both(ch: string): string {
  return ch.toLowerCase() + ch.toUpperCase();
}

/**
 * Rewrite a Python pattern for JavaScript: `\s` → ASCII whitespace, a `(?m)` prefix →
 * flag, and case-insensitivity compiled into the pattern itself (`b` → `[bB]`).
 *
 * Case is folded by hand rather than with the `i` flag or `(?i:...)` modifiers:
 * V8 13.6 drops the case-insensitivity of `(?i:bn|mn|tn|k|m|b|t)` after `\d+`, so
 * "$2.1B" silently lost its magnitude. Folding also keeps Python's ASCII-only
 * case rules, where the `i` flag would fold some non-ASCII letters.
 */
export function translate(pattern: string, ignoreCase = false): { source: string; multiline: boolean } {
  let multiline = false;
  if (pattern.startsWith("(?m)")) {
    multiline = true;
    pattern = pattern.slice(4);
  }
  let out = "";
  let inClass = false;
  const caseStack: boolean[] = [ignoreCase];
  const folding = () => caseStack[caseStack.length - 1];
  for (let i = 0; i < pattern.length; i++) {
    const ch = pattern[i];
    if (ch === "\\") {
      const next = pattern[i + 1];
      if (next === "s") {
        out += inClass ? WS : `[${WS}]`;
        i++;
      } else if (next === "x" || next === "u") {
        const width = next === "x" ? 2 : 4;
        out += pattern.slice(i, i + 2 + width);
        i += 1 + width;
      } else {
        out += ch + next;
        i++;
      }
      continue;
    }
    if (inClass) {
      if (ch === "]") {
        inClass = false;
        out += ch;
      } else if (folding() && ASCII_LETTER.test(ch) && pattern[i + 1] === "-" && ASCII_LETTER.test(pattern[i + 2] ?? "")) {
        const end = pattern[i + 2];
        out += `${ch.toLowerCase()}-${end.toLowerCase()}${ch.toUpperCase()}-${end.toUpperCase()}`;
        i += 2;
      } else {
        out += folding() && ASCII_LETTER.test(ch) ? both(ch) : ch;
      }
      continue;
    }
    if (ch === "[") {
      inClass = true;
      out += ch;
      if (pattern[i + 1] === "^") out += pattern[++i];
    } else if (pattern.startsWith("(?i:", i) || pattern.startsWith("(?-i:", i)) {
      caseStack.push(pattern[i + 2] === "i");
      out += "(?:";
      i += pattern[i + 2] === "i" ? 3 : 4;
    } else if (ch === "(") {
      caseStack.push(folding());
      out += ch;
      if (pattern[i + 1] === "?") {  // copy the group's "?:", "?=", "?<!" ... verbatim
        const head = /^\?(?:<[=!]|[:=!])/.exec(pattern.slice(i + 1))?.[0] ?? "";
        out += head;
        i += head.length;
      }
    } else if (ch === ")") {
      caseStack.pop();
      out += ch;
    } else if (multiline && ch === "^") {
      out += "(?<![^\\n])"; // Python's line start: after \n only (JS 'm' also breaks lines at \r, U+2028, U+2029)
    } else if (multiline && ch === "$") {
      out += "(?![^\\n])";
    } else if (folding() && ASCII_LETTER.test(ch)) {
      out += `[${both(ch)}]`;
    } else {
      out += ch;
    }
  }
  return { source: out, multiline };
}

export interface Pattern {
  /** All matches, left to right, with group offsets (Python `finditer`). */
  all(text: string): RegExpExecArray[];
  /** A match starting exactly at `pos`, or null (Python `pattern.match(text, pos)`). */
  at(text: string, pos: number): RegExpExecArray | null;
  /** Does the whole string match (Python `fullmatch`)? */
  whole(text: string): boolean;
  /** First match from `pos` on, or null (Python `search`). */
  search(text: string, pos?: number): RegExpExecArray | null;
}

export function compile(pattern: string, opts: { ignoreCase?: boolean } = {}): Pattern {
  const { source, multiline } = translate(pattern, opts.ignoreCase);
  const flags = "";
  const global = new RegExp(source, flags + "gd");
  const sticky = new RegExp(source, flags + "yd");
  const anchored = new RegExp(`^(?:${source})$`, flags);
  return {
    all(text) {
      global.lastIndex = 0;
      return [...text.matchAll(global)] as RegExpExecArray[];
    },
    at(text, pos) {
      sticky.lastIndex = pos;
      return sticky.exec(text);
    },
    whole(text) {
      return anchored.test(text);
    },
    search(text, pos = 0) {
      global.lastIndex = pos;
      return global.exec(text);
    },
  };
}

/** Python `re.escape` for the characters that can appear in our token lists. */
export function escape(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\/-]/g, "\\$&");
}

/** Python `_alternation`: longest first so `US$` wins over `$`. */
export function alternation(tokens: Iterable<string>): string {
  return [...tokens].sort((a, b) => b.length - a.length).map(escape).join("|");
}

/** Start and end offsets of group `g` (0 = the whole match). */
export function span(m: RegExpExecArray, g = 0): [number, number] {
  const ix = m.indices?.[g];
  if (!ix) throw new Error(`group ${g} did not participate`);
  return [ix[0], ix[1]];
}
