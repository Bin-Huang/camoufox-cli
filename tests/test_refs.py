"""Tests for ref registry: parsing aria snapshots and resolving refs."""

from camoufox_cli.refs import RefRegistry, RefEntry, INTERACTIVE_ROLES, UNNAMED_RE


class TestBuildFromSnapshot:
    def test_basic_snapshot(self):
        registry = RefRegistry()
        aria = '- link "About"\n- button "Submit"'
        result = registry.build_from_snapshot(aria)
        assert "[ref=e1]" in result
        assert "[ref=e2]" in result
        assert len(registry) == 2

    def test_assigns_roles_and_names(self):
        registry = RefRegistry()
        registry.build_from_snapshot('- link "Home"\n- button "OK"')
        entry = registry.resolve("e1")
        assert entry is not None
        assert entry.role == "link"
        assert entry.name == "Home"
        entry2 = registry.resolve("e2")
        assert entry2 is not None
        assert entry2.role == "button"
        assert entry2.name == "OK"

    def test_unnamed_elements(self):
        registry = RefRegistry()
        registry.build_from_snapshot("- img\n- link")
        entry = registry.resolve("e1")
        assert entry is not None
        assert entry.role == "img"
        assert entry.name == ""

    def test_name_with_escaped_quotes_and_backslash(self):
        registry = RefRegistry()
        registry.build_from_snapshot('- button "Say \\"hi\\""\n- button "a\\\\b"')
        assert registry.resolve("e1").name == 'Say "hi"'
        assert registry.resolve("e2").name == "a\\b"

    def test_single_quoted_key(self):
        # Playwright wraps keys containing ": " or " #" in YAML single quotes
        registry = RefRegistry()
        aria = "- 'button \"Step 1: Sign in\"'\n  - 'link \"It''s #42\"':\n    - /url: /x"
        result = registry.build_from_snapshot(aria, interactive_only=True)
        assert "[ref=e1]" in result
        assert "[ref=e2]" in result
        assert registry.resolve("e1").role == "button"
        assert registry.resolve("e1").name == "Step 1: Sign in"
        assert registry.resolve("e2").role == "link"
        assert registry.resolve("e2").name == "It's #42"

    def test_unquoted_slash_name(self):
        # Playwright writes a name that starts and ends with "/" without quotes
        registry = RefRegistry()
        aria = ("- link /about/:\n  - /url: /about/\n- button /a/b/ [disabled]\n"
                "- 'button /a: b/'\n- link /x/: /x/ text")
        result = registry.build_from_snapshot(aria, interactive_only=True)
        assert [registry.resolve(f"e{i}").name for i in range(1, 5)] == ["/about/", "/a/b/", "/a: b/", "/x/"]
        assert "- button /a/b/ [disabled] [ref=e2]" in result

    def test_single_slash_name(self):
        # A name of exactly "/" also starts and ends with "/", so Playwright
        # writes it unquoted. It must not merge with an unnamed sibling.
        registry = RefRegistry()
        aria = "- link /:\n  - /url: \"#a\"\n- link:\n  - /url: \"#b\"\n- button /abc/ [disabled]"
        result = registry.build_from_snapshot(aria, interactive_only=True)
        e1, e2, e3 = (registry.resolve(f"e{i}") for i in range(1, 4))
        assert (e1.role, e1.name, e1.nth) == ("link", "/", 0)
        assert (e2.role, e2.name, e2.nth) == ("link", "", 0)
        assert (e3.role, e3.name, e3.nth) == ("button", "/abc/", 0)
        assert "- link /: [ref=e1]" in result
        assert "- button /abc/ [disabled] [ref=e3]" in result

    def test_unnamed_re_matches_empty_and_omitted_names(self):
        # Playwright omits names longer than 900 characters
        assert UNNAMED_RE.search("")
        assert UNNAMED_RE.search("x" * 901)
        assert not UNNAMED_RE.search("x" * 900)
        assert not UNNAMED_RE.search("Submit")

    def test_nested_indentation(self):
        registry = RefRegistry()
        aria = '- list\n  - listitem\n    - link "Item 1"'
        result = registry.build_from_snapshot(aria)
        assert "[ref=e1]" in result  # list
        assert "[ref=e2]" in result  # listitem
        assert "[ref=e3]" in result  # link

    def test_nth_disambiguation(self):
        registry = RefRegistry()
        registry.build_from_snapshot('- link "Home"\n- link "Home"')
        e1 = registry.resolve("e1")
        e2 = registry.resolve("e2")
        assert e1 is not None and e2 is not None
        assert e1.nth == 0
        assert e2.nth == 1
        assert e1.role == e2.role == "link"
        assert e1.name == e2.name == "Home"

    def test_interactive_only(self):
        registry = RefRegistry()
        aria = '- heading "Title"\n- link "Click"\n- text: hello\n- button "OK"'
        result = registry.build_from_snapshot(aria, interactive_only=True)
        assert "Title" not in result
        assert "hello" not in result
        assert "Click" in result
        assert "OK" in result
        assert len(registry) == 2

    def test_clears_previous_entries(self):
        registry = RefRegistry()
        registry.build_from_snapshot('- link "A"')
        assert len(registry) == 1
        registry.build_from_snapshot('- button "B"\n- button "C"')
        assert len(registry) == 2
        assert registry.resolve("e1").role == "button"

    def test_non_matching_lines_preserved(self):
        registry = RefRegistry()
        result = registry.build_from_snapshot("plain text line\n- link \"A\"")
        assert "plain text line" in result
        assert "[ref=e1]" in result

    def test_scope_is_recorded_and_reset(self):
        registry = RefRegistry()
        registry.build_from_snapshot('- button "Delete"', scope="#list")
        assert registry.scope == "#list"
        registry.build_from_snapshot('- button "Delete"')
        assert registry.scope is None

    def test_empty_snapshot(self):
        registry = RefRegistry()
        result = registry.build_from_snapshot("")
        assert len(registry) == 0


class TestResolve:
    def test_with_at_prefix(self):
        registry = RefRegistry()
        registry.build_from_snapshot('- link "Test"')
        assert registry.resolve("@e1") is not None

    def test_without_at_prefix(self):
        registry = RefRegistry()
        registry.build_from_snapshot('- link "Test"')
        assert registry.resolve("e1") is not None

    def test_nonexistent_ref(self):
        registry = RefRegistry()
        registry.build_from_snapshot('- link "Test"')
        assert registry.resolve("e999") is None

    def test_empty_registry(self):
        registry = RefRegistry()
        assert registry.resolve("e1") is None


class TestInteractiveRoles:
    def test_common_interactive_roles(self):
        for role in ("link", "button", "textbox", "checkbox", "radio", "combobox", "tab"):
            assert role in INTERACTIVE_ROLES

    def test_non_interactive_roles(self):
        for role in ("heading", "img", "list", "listitem", "text", "paragraph"):
            assert role not in INTERACTIVE_ROLES
