from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api.errors import extract_retry_after_seconds, is_daily_free_tier_quota


class ServiceErrorsTests(unittest.TestCase):
    def test_extract_retry_after_seconds_reads_retry_delay(self) -> None:
        message = 'HTTP 429 {"error":{"details":[{"retryDelay":"11s"}]}}'

        self.assertEqual(extract_retry_after_seconds(message), 11)

    def test_extract_retry_after_seconds_rounds_up_fractional_seconds(self) -> None:
        message = "Please retry in 2.2s"

        self.assertEqual(extract_retry_after_seconds(message), 3)

    def test_daily_free_tier_quota_detection_matches_known_quota_ids(self) -> None:
        message = (
            "Quota exceeded for metric: generativelanguage.googleapis.com/"
            "generate_content_free_tier_requests quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier"
        )

        self.assertTrue(is_daily_free_tier_quota(message))

    def test_daily_free_tier_quota_detection_ignores_generic_quota_errors(self) -> None:
        self.assertFalse(is_daily_free_tier_quota("quota exceeded, check billing"))


if __name__ == "__main__":
    unittest.main()
