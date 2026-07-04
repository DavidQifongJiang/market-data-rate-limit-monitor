"""
Unit tests for rate-limit tracking, warnings, blocking, header parsing, and HTTP wrapping.
"""

import logging
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

from rate_limit_monitor import (
    HttpRateLimitedClient,
    RateLimitConfig,
    RateLimitExceededError,
    RateLimitMonitor,
)


class FakeResponse:
    """
    Simple response object used to test header parsing without real HTTP calls.
    """

    def __init__(self, headers=None):
        """
        Stores fake response headers for monitor tests.
        """

        self.headers = headers or {}


class TimeControlledMonitor(RateLimitMonitor):
    """
    Monitor subclass that allows tests to control the current time.
    """

    def __init__(self, config, now):
        """
        Stores a test-controlled timestamp before monitor initialization.
        """

        self.now = now
        super().__init__(config)

    def _now(self):
        """
        Returns the test-controlled timestamp instead of the real current time.
        """

        return self.now


class RateLimitMonitorTests(unittest.TestCase):
    """
    Tests for the core RateLimitMonitor behavior.
    """

    def test_tracks_minute_and_day_usage(self):
        """
        Verifies that each allowed request increments both minute and day counters.
        """

        monitor = RateLimitMonitor(
            RateLimitConfig(provider_name="Test", per_minute_limit=100, per_day_limit=1000)
        )

        monitor.before_request()
        monitor.before_request()

        self.assertEqual(monitor.minute_count, 2)
        self.assertEqual(monitor.day_count, 2)

    def test_warns_at_eighty_percent_internal_usage(self):
        """
        Verifies that internal usage logs a warning once it reaches 80%.
        """

        monitor = RateLimitMonitor(RateLimitConfig(provider_name="Test", per_minute_limit=10))

        with self.assertLogs("rate_limit_monitor.monitor", level=logging.WARNING) as logs:
            for _ in range(8):
                monitor.before_request()

        self.assertIn("Test minute rate-limit usage", "\n".join(logs.output))

    def test_warns_at_eighty_percent_daily_usage(self):
        """
        Verifies that daily usage logs a warning once it reaches 80%.
        """

        monitor = RateLimitMonitor(RateLimitConfig(provider_name="Test", per_day_limit=10))

        with self.assertLogs("rate_limit_monitor.monitor", level=logging.WARNING) as logs:
            for _ in range(8):
                monitor.before_request()

        self.assertIn("Test day rate-limit usage", "\n".join(logs.output))

    def test_warns_at_eighty_percent_per_minute_usage(self):
        """
        Verifies that per-minute usage logs a warning once it reaches 80%.
        """

        monitor = RateLimitMonitor(RateLimitConfig(provider_name="Test", per_minute_limit=10))

        with self.assertLogs("rate_limit_monitor.monitor", level=logging.WARNING) as logs:
            for _ in range(8):
                monitor.before_request()

        self.assertIn("Test minute rate-limit usage", "\n".join(logs.output))

    def test_blocks_at_ninety_five_percent_internal_usage(self):
        """
        Verifies that internal minute usage blocks new requests at 95%.
        """

        monitor = RateLimitMonitor(RateLimitConfig(provider_name="Test", per_minute_limit=100))

        with self.assertLogs("rate_limit_monitor.monitor", level=logging.WARNING):
            for _ in range(95):
                monitor.before_request()

        with self.assertRaisesRegex(RateLimitExceededError, "minute rate limit"):
            monitor.before_request()

    def test_blocks_at_ninety_five_percent_daily_usage(self):
        """
        Verifies that daily usage blocks new requests at 95%.
        """

        monitor = RateLimitMonitor(RateLimitConfig(provider_name="Test", per_day_limit=100))

        with self.assertLogs("rate_limit_monitor.monitor", level=logging.WARNING):
            for _ in range(95):
                monitor.before_request()

        with self.assertRaisesRegex(RateLimitExceededError, "day rate limit"):
            monitor.before_request()

    def test_blocks_at_ninety_five_percent_per_minute_usage(self):
        """
        Verifies that per-minute usage blocks new requests at 95%.
        """

        monitor = RateLimitMonitor(RateLimitConfig(provider_name="Test", per_minute_limit=100))

        with self.assertLogs("rate_limit_monitor.monitor", level=logging.WARNING):
            for _ in range(95):
                monitor.before_request()

        with self.assertRaisesRegex(RateLimitExceededError, "minute rate limit"):
            monitor.before_request()

    def test_resets_minute_counters(self):
        """
        Verifies that the minute counter resets when the UTC minute changes.
        """

        now = datetime(2026, 6, 29, 12, 0, 30, tzinfo=UTC)
        monitor = TimeControlledMonitor(
            RateLimitConfig(provider_name="Test", per_minute_limit=10),
            now,
        )
        monitor.before_request()
        monitor.before_request()

        monitor.now = now + timedelta(minutes=1)

        self.assertEqual(monitor.minute_count, 0)
        self.assertEqual(monitor.day_count, 2)

    def test_resets_daily_counters(self):
        """
        Verifies that the day counter resets when the UTC day changes.
        """

        now = datetime(2026, 6, 29, 23, 59, 30, tzinfo=UTC)
        monitor = TimeControlledMonitor(
            RateLimitConfig(provider_name="Test", per_day_limit=10),
            now,
        )
        monitor.before_request()
        monitor.before_request()

        monitor.now = now + timedelta(minutes=1)

        self.assertEqual(monitor.day_count, 0)
        self.assertEqual(monitor.minute_count, 0)

    def test_uses_provider_headers_when_available(self):
        """
        Verifies that provider-reported quota headers can trigger blocking.
        """

        monitor = RateLimitMonitor(RateLimitConfig(provider_name="Header Provider"))
        with self.assertLogs("rate_limit_monitor.monitor", level=logging.WARNING):
            monitor.after_response(
                FakeResponse(
                    {
                        "X-RateLimit-Limit": "100",
                        "X-RateLimit-Remaining": "5",
                    }
                )
            )

        with self.assertRaisesRegex(RateLimitExceededError, "provider-reported quota"):
            monitor.before_request()

    def test_parses_remaining_quota_from_response_headers(self):
        """
        Verifies that limit and remaining headers are stored in the usage snapshot.
        """

        monitor = RateLimitMonitor(RateLimitConfig(provider_name="Header Provider"))

        monitor.after_response(
            FakeResponse(
                {
                    "X-RateLimit-Limit": "100",
                    "X-RateLimit-Remaining": "25",
                }
            )
        )

        self.assertEqual(
            monitor.usage_snapshot(),
            {
                "minute_count": 0,
                "day_count": 0,
                "header_limit": 100,
                "header_remaining": 25,
            },
        )

    def test_supports_configurable_header_names(self):
        """
        Verifies that custom provider header names can be configured.
        """

        config = RateLimitConfig(
            provider_name="Custom Provider",
            remaining_header_names=("Api-Remaining",),
            limit_header_names=("Api-Limit",),
        )
        monitor = RateLimitMonitor(config)

        with self.assertLogs("rate_limit_monitor.monitor", level=logging.WARNING) as logs:
            monitor.after_response(FakeResponse({"Api-Limit": "50", "Api-Remaining": "10"}))

        self.assertIn("provider-reported rate-limit usage", "\n".join(logs.output))

    def test_retry_after_blocks_future_requests(self):
        """
        Verifies that Retry-After headers block requests until the wait time expires.
        """

        monitor = RateLimitMonitor(RateLimitConfig(provider_name="Retry Provider"))
        monitor.after_response(FakeResponse({"Retry-After": "60"}))

        with self.assertRaisesRegex(RateLimitExceededError, "retry after"):
            monitor.before_request()

    def test_missing_headers_fall_back_to_internal_counters(self):
        """
        Verifies that missing response headers do not disable internal counting.
        """

        monitor = RateLimitMonitor(RateLimitConfig(provider_name="No Headers", per_minute_limit=3))

        monitor.after_response(FakeResponse())
        monitor.before_request()

        self.assertEqual(monitor.minute_count, 1)

    def test_fallback_behavior_when_no_headers_exist(self):
        """
        Verifies snapshot values when only internal counters are available.
        """

        monitor = RateLimitMonitor(
            RateLimitConfig(provider_name="No Headers", per_minute_limit=10, per_day_limit=100)
        )

        monitor.after_response(FakeResponse())
        monitor.before_request()
        snapshot = monitor.usage_snapshot()

        self.assertEqual(snapshot["minute_count"], 1)
        self.assertEqual(snapshot["day_count"], 1)
        self.assertIsNone(snapshot["header_limit"])
        self.assertIsNone(snapshot["header_remaining"])


class HttpRateLimitedClientTests(unittest.TestCase):
    """
    Tests for the HTTP client wrapper around requests.
    """

    def test_client_calls_monitor_before_and_after_response(self):
        """
        Verifies that the HTTP client checks before request and updates after response.
        """

        monitor = Mock()
        response = FakeResponse()
        session = Mock()
        session.request.return_value = response

        client = HttpRateLimitedClient(monitor, session=session)
        result = client.get("https://example.test/data", timeout=1)

        self.assertIs(result, response)
        monitor.before_request.assert_called_once_with()
        session.request.assert_called_once_with("GET", "https://example.test/data", timeout=1)
        monitor.after_response.assert_called_once_with(response)

    def test_client_does_not_send_when_monitor_blocks(self):
        """
        Verifies that no HTTP request is sent when the monitor blocks first.
        """

        monitor = Mock()
        monitor.before_request.side_effect = RateLimitExceededError("blocked")
        session = Mock()

        client = HttpRateLimitedClient(monitor, session=session)

        with self.assertRaises(RateLimitExceededError):
            client.get("https://example.test/data")
        session.request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
