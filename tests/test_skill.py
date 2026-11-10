"""Tests for `camoufox-cli skill` and the stale-skill hint."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from camoufox_cli import config
from camoufox_cli.cli import build_command
from camoufox_cli import skill
from camoufox_cli.skill import TOPICS, render_guide, unknown_command_message

REPO = Path(__file__).resolve().parent.parent

# Claude Code keeps 30,000 characters of command output. Leave headroom so the
# end line, which agents use to detect truncation, is never cut off.
MAX_GUIDE_CHARS = 25_000


@pytest.fixture(autouse=True)
def config_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", str(tmp_path / "config.json"))


class TestBuildSkillCommand:
    def test_default_topic(self):
        assert build_command("skill", ["skill"]) == {"id": "r1", "action": "skill", "params": {"topic": "usage"}}

    @pytest.mark.parametrize("topic", TOPICS)
    def test_each_topic(self, topic):
        assert build_command("skill", ["skill", topic])["params"] == {"topic": topic}

    def test_unknown_topic_exits(self, capsys):
        with pytest.raises(SystemExit):
            build_command("skill", ["skill", "nope"])
        err = capsys.readouterr().err
        assert err.startswith("Unknown topic: nope\n")
        assert "Usage: camoufox-cli skill" in err

    def test_extra_argument_exits(self):
        with pytest.raises(SystemExit):
            build_command("skill", ["skill", "commands", "extra"])


class TestRenderGuide:
    @pytest.mark.parametrize("topic", TOPICS)
    def test_markers_wrap_the_source(self, topic):
        guide = render_guide(topic, "1.2.3")
        source = (REPO / "src" / "camoufox_cli" / "guide" / f"{topic}.md").read_text(encoding="utf-8")
        assert guide == (
            f"[camoufox-cli:skill] {topic} guide v1.2.3\n\n"
            f"{source.strip()}\n\n"
            f"[camoufox-cli:skill] end of {topic} guide v1.2.3\n"
        )

    @pytest.mark.parametrize("topic", TOPICS)
    def test_fits_agent_output_limit(self, topic):
        assert len(render_guide(topic, "0.0.0")) < MAX_GUIDE_CHARS

    def test_guide_has_no_frontmatter(self):
        assert not render_guide("usage", "0.0.0").split("\n", 2)[2].startswith("---")

    def test_usage_guide_names_every_topic_command(self):
        guide = render_guide("usage", "0.0.0")
        for topic in TOPICS[1:]:
            assert f"camoufox-cli skill {topic}" in guide


class TestEntrySkill:
    """The published skill only bootstraps; the guide must not live there too."""

    def test_entry_skill_defers_to_skill_command(self):
        text = (REPO / "skills" / "camoufox-cli" / "SKILL.md").read_text(encoding="utf-8")
        assert re.search(r"^name: camoufox-cli$", text, re.M)
        assert "camoufox-cli skill" in text
        assert "[camoufox-cli:skill] end of" in text
        assert len(text) < 5_000

    def test_entry_skill_has_only_the_bootstrap_file(self):
        files = sorted(p.name for p in (REPO / "skills" / "camoufox-cli").rglob("*") if p.is_file())
        assert files == ["SKILL.md"]


class TestHelp:
    @pytest.mark.parametrize("rest", [["--help"], ["-h"], ["help"], ["click", "--help"], ["snapshot", "-h"]])
    def test_prints_usage_and_exits_zero(self, rest, capsys):
        with pytest.raises(SystemExit) as exc:
            build_command(rest[0], rest)
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert out.startswith("Usage: camoufox-cli [flags]")
        assert "skill [topic]" in out

    @pytest.mark.parametrize("rest", [["fill", "@e1", "--help"], ["type", "@e1", "-h"], ["eval", "1", "--help"],
                                      ["text", "help"], ["eval", "help"]])
    def test_help_as_a_value_is_passed_through(self, rest):
        assert build_command(rest[0], rest)["action"] == rest[0]


class TestSkillProcess:
    """Run the real entry point: the guide reaches stdout, nothing starts a daemon."""

    def run(self, *args, tmp_path):
        env = {**os.environ, "CAMOUFOX_CLI_CONFIG": str(tmp_path / "config.json")}
        return subprocess.run(
            [sys.executable, "-c", "from camoufox_cli.cli import main; main()", *args],
            capture_output=True, text=True, env=env, timeout=30,
        )

    def test_skill_prints_guide(self, tmp_path):
        res = self.run("skill", tmp_path=tmp_path)
        assert res.returncode == 0
        assert res.stdout.startswith("[camoufox-cli:skill] usage guide v")
        assert res.stdout.rstrip().splitlines()[-1].startswith("[camoufox-cli:skill] end of usage guide v")

    def test_flags_before_skill(self, tmp_path):
        res = self.run("--session", "unused-skill-test", "--tab", "x", "skill", "commands", tmp_path=tmp_path)
        assert res.returncode == 0
        assert res.stdout.startswith("[camoufox-cli:skill] commands guide v")


class TestJsParity:
    """The JS CLI keeps its own copy of these constants; they must match."""

    JS = (REPO / "js" / "src" / "skill.ts").read_text(encoding="utf-8")

    def test_topics_and_help_args(self):
        assert f"TOPICS = {json.dumps(list(TOPICS))} as const" in self.JS
        assert json.dumps(list(skill.HELP_ARGS)) in self.JS
        assert json.dumps(list(skill.HELP_FLAGS)) in self.JS

    def test_messages(self):
        assert json.dumps(skill.SKILL_USAGE) in self.JS
        for name, text in skill.REMOVED_COMMANDS.items():
            assert f'"{name}": {json.dumps(text)}' in self.JS


class TestUnknownCommand:
    def test_hint_points_to_skill(self):
        msg = unknown_command_message("frobnicate", "1.2.3")
        assert msg.startswith("Unknown command: frobnicate\n")
        assert "If a skill or guide told you to run this" in msg
        assert "camoufox-cli v1.2.3" in msg
        assert "Run `camoufox-cli skill`" in msg

    def test_flag_and_value_in_one_argument(self):
        msg = unknown_command_message("--tab scan-1a2b", "1.2.3")
        assert "reached camoufox-cli as one argument" in msg
        assert "camoufox-cli skill" not in msg

    @pytest.mark.parametrize("name", ["toString", "constructor", "__class__"])
    def test_object_attribute_names_are_not_removed_commands(self, name):
        assert "was removed" not in unknown_command_message(name, "1.2.3")

    def test_removed_command_names_replacement(self):
        msg = unknown_command_message("close-tab", "1.2.3")
        assert "`close-tab` was removed" in msg
        assert "--tab <name> close" in msg

    def test_build_command_prints_hint(self, capsys):
        with pytest.raises(SystemExit):
            build_command("close-tab", ["close-tab"])
        err = capsys.readouterr().err
        assert "`close-tab` was removed" in err
        assert "Usage: camoufox-cli [flags]" in err
