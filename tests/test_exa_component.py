from __future__ import annotations

import unittest

from components.exa import build_search_payload


class BuildSearchPayloadTests(unittest.TestCase):
    def test_defaults_use_auto_and_highlights(self) -> None:
        payload = build_search_payload(
            keywords="latest ai safety updates",
            num_results=50,
            search_type="auto",
            content_mode="highlights",
            max_characters=1400,
            max_age_hours=None,
            include_domains_csv="",
            exclude_domains_csv="",
            category="",
            system_prompt="",
            output_schema_json="",
            summary_query="",
        )

        self.assertEqual(payload["query"], "latest ai safety updates")
        self.assertEqual(payload["numResults"], 50)
        self.assertEqual(payload["type"], "auto")
        self.assertEqual(payload["contents"]["highlights"]["maxCharacters"], 1400)
        self.assertNotIn("maxAgeHours", payload["contents"])

    def test_invalid_type_falls_back_to_auto_and_parses_filters(self) -> None:
        payload = build_search_payload(
            keywords="agentic coding benchmarks",
            num_results=101,
            search_type="wrong-type",
            content_mode="summary",
            max_characters=2000,
            max_age_hours=0,
            include_domains_csv="arxiv.org, github.com",
            exclude_domains_csv="pinterest.com",
            category="news",
            system_prompt="prefer official sources",
            output_schema_json='{"type":"object","properties":{"items":{"type":"array"}}}',
            summary_query="key points",
        )

        self.assertEqual(payload["type"], "auto")
        self.assertEqual(payload["numResults"], 100)
        self.assertEqual(payload["includeDomains"], ["arxiv.org", "github.com"])
        self.assertEqual(payload["excludeDomains"], ["pinterest.com"])
        self.assertEqual(payload["category"], "news")
        self.assertEqual(payload["systemPrompt"], "prefer official sources")
        self.assertEqual(payload["contents"]["maxAgeHours"], 0)
        self.assertEqual(payload["contents"]["summary"]["query"], "key points")
        self.assertIn("outputSchema", payload)


if __name__ == "__main__":
    unittest.main()
