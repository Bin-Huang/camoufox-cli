"""Tests for JSON-line protocol."""

from camoufox_cli.protocol import parse_command, serialize_response, ok_response, error_response


class TestParseCommand:
    def test_basic(self):
        result = parse_command('{"action": "open", "params": {"url": "https://example.com"}}')
        assert result == {"action": "open", "params": {"url": "https://example.com"}}

    def test_with_whitespace(self):
        result = parse_command('  {"action": "close"}  \n')
        assert result == {"action": "close"}

    def test_unicode(self):
        result = parse_command('{"action": "fill", "params": {"text": "你好"}}')
        assert result["params"]["text"] == "你好"

    def test_invalid_json(self):
        import pytest
        with pytest.raises(Exception):
            parse_command("not json")


class TestSerializeResponse:
    def test_basic(self):
        resp = {"id": "r1", "success": True}
        result = serialize_response(resp)
        assert result == b'{"id": "r1", "success": true}\n'

    def test_unicode(self):
        resp = {"id": "r1", "success": True, "data": {"title": "腾讯网"}}
        result = serialize_response(resp)
        assert "腾讯网" in result.decode("utf-8")
        assert b"\\u" not in result  # ensure_ascii=False

    def test_ends_with_newline(self):
        result = serialize_response({"id": "r1"})
        assert result.endswith(b"\n")


class TestOkResponse:
    def test_without_data(self):
        resp = ok_response("r1")
        assert resp == {"id": "r1", "success": True}

    def test_with_data(self):
        resp = ok_response("r1", {"url": "https://example.com"})
        assert resp == {"id": "r1", "success": True, "data": {"url": "https://example.com"}}

    def test_with_none_data(self):
        resp = ok_response("r1", None)
        assert "data" not in resp


class TestErrorResponse:
    def test_basic(self):
        resp = error_response("r1", "something went wrong")
        assert resp == {"id": "r1", "success": False, "error": "something went wrong"}

    def test_preserves_id(self):
        resp = error_response("abc123", "err")
        assert resp["id"] == "abc123"
