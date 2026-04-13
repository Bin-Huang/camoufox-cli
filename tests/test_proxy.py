import pytest

from camoufox_cli.proxy import parse_proxy_settings


class TestParseProxySettings:
    def test_http_proxy_without_auth(self):
        proxy = parse_proxy_settings("http://host:8080")
        assert proxy == {"server": "http://host:8080"}

    def test_authenticated_http_proxy_returns_credentials(self):
        proxy = parse_proxy_settings("http://user:pass@host:8080")
        assert proxy == {
            "server": "http://host:8080",
            "username": "user",
            "password": "pass",
        }

    def test_percent_encoded_credentials_are_decoded(self):
        proxy = parse_proxy_settings("http://user%40x:pass%2Fword@host:8080")
        assert proxy == {
            "server": "http://host:8080",
            "username": "user@x",
            "password": "pass/word",
        }

    def test_https_scheme_is_rejected(self):
        with pytest.raises(ValueError, match="Only http://"):
            parse_proxy_settings("https://user:pass@host:443")
