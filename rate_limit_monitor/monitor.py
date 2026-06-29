from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from math import ceil
from typing import Mapping

from .config import RateLimitConfig
from .exceptions import RateLimitExceededError

logger = logging.getLogger(__name__)


@dataclass
class _WindowCounter:
    window_start: datetime
    count: int = 0


@dataclass
class _HeaderQuota:
    limit: int
    remaining: int

    @property
    def used(self) -> int:
        return max(self.limit - self.remaining, 0)


class RateLimitMonitor:
    def __init__(self, config: RateLimitConfig) -> None:
        self.config = config
        now = self._now()
        self._minute = _WindowCounter(self._minute_start(now))
        self._day = _WindowCounter(self._day_start(now))
        self._header_quota: _HeaderQuota | None = None
        self._retry_after_until: datetime | None = None
        self._warned_internal: set[str] = set()
        self._warned_header_key: tuple[int, int] | None = None

    @property
    def minute_count(self) -> int:
        self._reset_expired_windows()
        return self._minute.count

    @property
    def day_count(self) -> int:
        self._reset_expired_windows()
        return self._day.count

    def before_request(self) -> None:
        self._reset_expired_windows()
        self._raise_if_retry_after_active()
        self._raise_if_blocked_by_headers()
        self._raise_if_internal_limit_reached()

        self._minute.count += 1
        self._day.count += 1
        self._warn_if_internal_usage_high()

    def after_response(self, response: object) -> None:
        headers = self._extract_headers(response)
        if not headers:
            return

        retry_after = self._first_header_value(headers, self.config.retry_after_header_names)
        if retry_after is not None:
            self._retry_after_until = self._parse_retry_after(retry_after)

        remaining = self._parse_int(
            self._first_header_value(headers, self.config.remaining_header_names)
        )
        limit = self._parse_int(self._first_header_value(headers, self.config.limit_header_names))
        if remaining is None or limit is None or limit <= 0:
            return

        self._header_quota = _HeaderQuota(limit=limit, remaining=max(remaining, 0))
        self._warn_if_header_usage_high()

    def usage_snapshot(self) -> dict[str, int | None]:
        self._reset_expired_windows()
        return {
            "minute_count": self._minute.count,
            "day_count": self._day.count,
            "header_limit": self._header_quota.limit if self._header_quota else None,
            "header_remaining": self._header_quota.remaining if self._header_quota else None,
        }

    def _raise_if_internal_limit_reached(self) -> None:
        self._raise_if_count_reached("minute", self._minute.count, self.config.per_minute_limit)
        self._raise_if_count_reached("day", self._day.count, self.config.per_day_limit)

    def _raise_if_count_reached(self, name: str, count: int, limit: int | None) -> None:
        if limit is None:
            return
        threshold = ceil(limit * self.config.block_threshold)
        if count >= threshold:
            raise RateLimitExceededError(
                f"{self.config.provider_name} {name} rate limit is at or above "
                f"{self.config.block_threshold:.0%}: {count}/{limit} requests used"
            )

    def _raise_if_blocked_by_headers(self) -> None:
        if self._header_quota is None:
            return
        if self._header_quota.used >= ceil(self._header_quota.limit * self.config.block_threshold):
            raise RateLimitExceededError(
                f"{self.config.provider_name} provider-reported quota is at or above "
                f"{self.config.block_threshold:.0%}: "
                f"{self._header_quota.used}/{self._header_quota.limit} requests used"
            )

    def _raise_if_retry_after_active(self) -> None:
        if self._retry_after_until is None:
            return
        now = self._now()
        if now < self._retry_after_until:
            seconds = ceil((self._retry_after_until - now).total_seconds())
            raise RateLimitExceededError(
                f"{self.config.provider_name} requested retry after {seconds} seconds"
            )
        self._retry_after_until = None

    def _warn_if_internal_usage_high(self) -> None:
        self._warn_if_count_high("minute", self._minute.count, self.config.per_minute_limit)
        self._warn_if_count_high("day", self._day.count, self.config.per_day_limit)

    def _warn_if_count_high(self, name: str, count: int, limit: int | None) -> None:
        if limit is None:
            return
        if name in self._warned_internal:
            return
        if count >= ceil(limit * self.config.warning_threshold):
            self._warned_internal.add(name)
            logger.warning(
                "%s %s rate-limit usage is at or above %.0f%%: %s/%s requests used",
                self.config.provider_name,
                name,
                self.config.warning_threshold * 100,
                count,
                limit,
            )

    def _warn_if_header_usage_high(self) -> None:
        if self._header_quota is None:
            return
        quota_key = (self._header_quota.limit, self._header_quota.remaining)
        if (
            self._header_quota.used >= ceil(self._header_quota.limit * self.config.warning_threshold)
            and quota_key != self._warned_header_key
        ):
            self._warned_header_key = quota_key
            logger.warning(
                "%s provider-reported rate-limit usage is at or above %.0f%%: "
                "%s/%s requests used",
                self.config.provider_name,
                self.config.warning_threshold * 100,
                self._header_quota.used,
                self._header_quota.limit,
            )

    def _reset_expired_windows(self) -> None:
        now = self._now()
        minute_start = self._minute_start(now)
        day_start = self._day_start(now)
        if minute_start != self._minute.window_start:
            self._minute = _WindowCounter(minute_start)
            self._warned_internal.discard("minute")
        if day_start != self._day.window_start:
            self._day = _WindowCounter(day_start)
            self._warned_internal.discard("day")

    def _extract_headers(self, response: object) -> Mapping[str, object]:
        headers = getattr(response, "headers", None)
        return headers if isinstance(headers, Mapping) else {}

    def _first_header_value(
        self, headers: Mapping[str, object], names: tuple[str, ...] | list[str]
    ) -> str | None:
        lower_headers = {key.lower(): value for key, value in headers.items()}
        for name in names:
            value = lower_headers.get(name.lower())
            if value is not None:
                return str(value)
        return None

    def _parse_retry_after(self, value: str) -> datetime:
        seconds = self._parse_int(value)
        if seconds is not None:
            return self._now() + timedelta(seconds=max(seconds, 0))
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return self._now()
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _parse_int(self, value: str | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _minute_start(self, value: datetime) -> datetime:
        return value.replace(second=0, microsecond=0)

    def _day_start(self, value: datetime) -> datetime:
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
