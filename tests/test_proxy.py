from camoufox_cli.proxy import parse_proxy_settings


class TestParseProxySettings:
    def test_authenticated_https_proxy_keeps_credentials_without_extra_headers(self):
        proxy = parse_proxy_settings("https://user:pass@host:443")
        assert proxy == {
            "server": "https://host",
            "username": "user",
            "password": "pass",
        }

    def test_authenticated_http_proxy_does_not_add_extra_headers(self):
        proxy = parse_proxy_settings("http://user:pass@host:8080")
        assert proxy == {
            "server": "http://host:8080",
            "username": "user",
            "password": "pass",
        }

    def test_percent_encoded_credentials_are_decoded(self):
        proxy = parse_proxy_settings("https://user%40x:pass%2Fword@host:443")
        assert proxy == {
            "server": "https://host",
            "username": "user@x",
            "password": "pass/word",
        }
