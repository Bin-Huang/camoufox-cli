/** Ref registry: maps @e1, @e2 to aria role+name for Playwright locators. */

export interface RefEntry {
  ref: string;
  role: string;
  name: string;
  nth: number;
}

const INTERACTIVE_ROLES = new Set([
  "link", "button", "combobox", "textbox", "textarea",
  "checkbox", "radio", "switch", "slider",
  "tab", "tabpanel", "menuitem", "option",
  "select", "listbox", "searchbox",
]);

// Playwright renders each node as `- role "name" [attrs]`, with the name
// JSON-encoded, except that a name which starts and ends with "/" is written
// as is. If the key contains YAML-special text (e.g. ": " or " #"), the whole
// key is wrapped in YAML single quotes, with ' escaped as ''. A plain key never
// contains ":" followed by whitespace, so that marks where its value starts.
const ARIA_ITEM_RE = /^\s*-\s+(?:'((?:[^']|'')*)'|((?:[^:]|:(?!\s|$))*))/;
const ARIA_KEY_RE = /^(\w+)(?:\s+("(?:[^"\\]|\\.)*"|\/.*\/(?=(?:\s\[[^\]]*\])*$)))?/;

// Playwright omits names longer than 900 characters, so an unnamed node is an
// element whose accessible name is empty or over that limit.
export const UNNAMED_RE = /^$|^[\s\S]{901,}$/;

function parseAriaLine(line: string): { role: string; name: string } | null {
  const item = line.match(ARIA_ITEM_RE);
  if (!item) return null;
  const key = item[1] !== undefined ? item[1].replace(/''/g, "'") : item[2];
  const m = key.match(ARIA_KEY_RE);
  if (!m) return null;
  const name = m[2] ?? "";
  return { role: m[1], name: name.startsWith('"') ? JSON.parse(name) : name };
}

export class RefRegistry {
  private entries = new Map<string, RefEntry>();
  private counter = 0;
  /** Selector of the scoped snapshot (`snapshot -s`); refs resolve within it. */
  scope: string | undefined;

  buildFromSnapshot(ariaText: string, interactiveOnly: boolean = false, scope?: string): string {
    this.entries.clear();
    this.counter = 0;
    this.scope = scope;

    const seen = new Map<string, number>();
    const lines = ariaText.split("\n");
    const resultLines: string[] = [];

    for (const line of lines) {
      const parsed = parseAriaLine(line);
      if (!parsed) {
        if (!interactiveOnly) resultLines.push(line);
        continue;
      }

      const { role, name } = parsed;

      if (interactiveOnly && !INTERACTIVE_ROLES.has(role)) continue;

      const key = `${role}\0${name}`;
      const nth = seen.get(key) || 0;
      seen.set(key, nth + 1);

      this.counter++;
      const ref = `e${this.counter}`;
      this.entries.set(ref, { ref, role, name, nth });

      resultLines.push(`${line.trimEnd()} [ref=${ref}]`);
    }

    return resultLines.join("\n");
  }

  resolve(refStr: string): RefEntry | undefined {
    const ref = refStr.replace(/^@/, "");
    return this.entries.get(ref);
  }

  get size(): number {
    return this.entries.size;
  }
}
