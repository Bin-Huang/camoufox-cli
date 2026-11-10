"""Usage guide that `camoufox-cli skill` prints.

The guide ships inside the package, so an agent always reads the guide for the
installed CLI version. The entry skill in skills/camoufox-cli only tells agents
to run `camoufox-cli skill`. Every `npm pack` copies this guide directory into
the JS package, which prints the same bytes.
"""

from importlib.resources import files

TOPICS = ("usage", "commands", "snapshot-refs")
SKILL_USAGE = "Usage: camoufox-cli skill [commands|snapshot-refs]"


def unknown_topic_message(topic: str) -> str:
    return f"Unknown topic: {topic}\n{SKILL_USAGE}"


HELP_ARGS = ("help", "--help", "-h")
# After a command, only flags ask for help: `text help` targets a selector named "help".
HELP_FLAGS = ("--help", "-h")

# Commands that older guides taught. An agent with a stale skill still runs them.
REMOVED_COMMANDS = {
    "close-tab": "`close` now closes only your tab; use `--tab <name> close` for a named tab",
}


def render_guide(topic: str, version: str) -> str:
    """The guide for `topic`, between a version line and an end line.

    Agents check for the end line to detect truncated command output.
    """
    path = files("camoufox_cli").joinpath("guide", f"{topic}.md")
    try:
        body = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"Error: the usage guide is missing from this install ({path}). Reinstall camoufox-cli.")
    return (
        f"[camoufox-cli:skill] {topic} guide v{version}\n\n"
        f"{body.strip()}\n\n"
        f"[camoufox-cli:skill] end of {topic} guide v{version}\n"
    )


def unknown_command_message(action: str, version: str) -> str:
    """Error text for an unknown command, with a hint for agents whose skill is stale."""
    lines = [f"Unknown command: {action}"]
    if action.startswith("-") and " " in action:
        # e.g. T="--tab x"; camoufox-cli $T ...  (zsh does not split $T into words)
        lines.append(
            f"`{action}` reached camoufox-cli as one argument. Pass the flag and its value "
            "as two arguments. zsh does not split an unquoted $VAR into words."
        )
        return "\n".join(lines)
    if action in REMOVED_COMMANDS:
        lines.append(f"`{action}` was removed: {REMOVED_COMMANDS[action]}.")
    lines.append(
        f"If a skill or guide told you to run this, it may not match camoufox-cli v{version}. "
        "Run `camoufox-cli skill` to read the guide for this version."
    )
    return "\n".join(lines)
