"""Ref registry: maps @e1, @e2 to aria role+name for Playwright locators."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass
class RefEntry:
    ref: str        # e.g. "e1"
    role: str       # e.g. "link"
    name: str       # e.g. "About"
    nth: int = 0    # index for duplicates


# Roles considered "interactive" for snapshot -i
INTERACTIVE_ROLES = frozenset({
    "link", "button", "combobox", "textbox", "textarea",
    "checkbox", "radio", "switch", "slider",
    "tab", "tabpanel", "menuitem", "option",
    "select", "listbox", "searchbox",
})

# Playwright renders each node as `- role "name"`, with the name JSON-encoded.
# If the key contains YAML-special text (e.g. ": " or " #"), the whole key is
# wrapped in YAML single quotes, with ' escaped as ''.
_ARIA_ITEM_RE = re.compile(
    r"^\s*-\s+"                     # leading indent + dash
    r"(?:'((?:[^']|'')*)'|(.*))"     # single-quoted key, or plain key
)
_ARIA_KEY_RE = re.compile(
    r'^(\w+)'                        # role
    r'(?:\s+("(?:[^"\\]|\\.)*"))?'   # optional JSON-encoded name
)


def _parse_aria_line(line: str) -> tuple[str, str] | None:
    """Return (role, name) for an aria snapshot node line, or None."""
    item = _ARIA_ITEM_RE.match(line)
    if not item:
        return None
    key = item.group(1).replace("''", "'") if item.group(1) is not None else item.group(2)
    m = _ARIA_KEY_RE.match(key)
    if not m:
        return None
    return m.group(1), json.loads(m.group(2)) if m.group(2) else ""


class RefRegistry:
    def __init__(self):
        self._entries: dict[str, RefEntry] = {}  # ref_str -> RefEntry
        self._counter = 0
        self.scope: str | None = None  # selector of a scoped snapshot; refs resolve within it

    def build_from_snapshot(self, aria_text: str, interactive_only: bool = False, scope: str | None = None) -> str:
        """Parse aria snapshot text, assign refs, return annotated text."""
        self._entries.clear()
        self._counter = 0
        self.scope = scope

        # Track role+name occurrences for nth disambiguation
        seen: dict[tuple[str, str], int] = {}
        lines = aria_text.split("\n")
        result_lines = []

        for line in lines:
            parsed = _parse_aria_line(line)
            if parsed is None:
                if not interactive_only:
                    result_lines.append(line)
                continue

            role, name = parsed

            if interactive_only and role not in INTERACTIVE_ROLES:
                continue

            key = (role, name)
            nth = seen.get(key, 0)
            seen[key] = nth + 1

            self._counter += 1
            ref = f"e{self._counter}"
            entry = RefEntry(ref=ref, role=role, name=name, nth=nth)
            self._entries[ref] = entry

            # Append [ref=eN] to the line
            annotated = f"{line.rstrip()} [ref={ref}]"
            result_lines.append(annotated)

        return "\n".join(result_lines)

    def resolve(self, ref_str: str) -> RefEntry | None:
        """Resolve a ref string like 'e1' or '@e1' to a RefEntry."""
        ref = ref_str.lstrip("@")
        return self._entries.get(ref)

    def __len__(self) -> int:
        return len(self._entries)
