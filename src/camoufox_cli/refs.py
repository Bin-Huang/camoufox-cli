"""Ref registry: maps @e1, @e2 to aria role+name for Playwright locators."""

from __future__ import annotations

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

# Pattern to match aria snapshot lines like:  - link "About"
#   handles nested indentation and optional attributes
_ARIA_LINE_RE = re.compile(
    r'^(\s*-\s+)'           # leading indent + dash
    r'(\w+)'                # role
    r'(?:\s+"([^"]*)")?'    # optional quoted name
)


class RefRegistry:
    def __init__(self):
        self._entries: dict[str, RefEntry] = {}  # ref_str -> RefEntry
        self._counter = 0

    def build_from_snapshot(self, aria_text: str, interactive_only: bool = False) -> str:
        """Parse aria snapshot text, assign refs, return annotated text."""
        self._entries.clear()
        self._counter = 0

        # Track role+name occurrences for nth disambiguation
        seen: dict[tuple[str, str], int] = {}
        lines = aria_text.split("\n")
        result_lines = []

        for line in lines:
            m = _ARIA_LINE_RE.match(line)
            if not m:
                if not interactive_only:
                    result_lines.append(line)
                continue

            role = m.group(2)
            name = m.group(3) or ""

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
