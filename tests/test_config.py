import unittest

from src.core.config import origin_is_allowed, resolve_allowed_origin


class ConfigCorsTests(unittest.TestCase):
    def test_origin_is_allowed_supports_exact_match(self):
        patterns = ["https://app.example.com"]
        self.assertTrue(origin_is_allowed("https://app.example.com", patterns))
        self.assertFalse(origin_is_allowed("https://other.example.com", patterns))

    def test_origin_is_allowed_supports_subdomain_wildcards(self):
        patterns = ["https://*.example.com"]
        self.assertTrue(origin_is_allowed("https://demo.example.com", patterns))
        self.assertFalse(origin_is_allowed("https://example.com", patterns))

    def test_resolve_allowed_origin_returns_wildcard_when_enabled(self):
        self.assertEqual(resolve_allowed_origin("https://app.example.com", ["*"]), "*")
        self.assertEqual(resolve_allowed_origin(None, ["*"]), "*")

    def test_resolve_allowed_origin_ignores_missing_origin_without_wildcard(self):
        self.assertIsNone(resolve_allowed_origin(None, ["https://app.example.com"]))


if __name__ == "__main__":
    unittest.main()
