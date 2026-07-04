from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True)
class RateLimitConfig:
    """
    Configuration for one market data API provider.

    provider_name:
        Human-readable provider name used in warning and error messages.

    per_minute_limit:
        Optional maximum number of requests allowed per UTC minute.
        Use None when the provider does not publish a per-minute quota.

    per_day_limit:
        Optional maximum number of requests allowed per UTC day.
        Use None when the provider does not publish a daily quota.

    warning_threshold:
        Usage percentage that triggers a warning log.
        Default is 0.80, meaning 80% of the configured quota.

    block_threshold:
        Usage percentage that blocks future requests.
        Default is 0.95, meaning 95% of the configured quota.

    remaining_header_names:
        Response header names that may contain remaining provider quota.

    limit_header_names:
        Response header names that may contain total provider quota.

    retry_after_header_names:
        Response header names that tell the client how long to wait before retrying.

    __post_init__ is automatically called after the dataclass object is created. We use it to reject bad settings early.
    """
    provider_name: str = "market-data-provider"
    per_minute_limit: int | None = None
    per_day_limit: int | None = None
    warning_threshold: float = 0.80
    block_threshold: float = 0.95
    remaining_header_names: Sequence[str] = field(
        default_factory=lambda: (
            "X-RateLimit-Remaining",
            "RateLimit-Remaining",
        )
    )
    limit_header_names: Sequence[str] = field(
        default_factory=lambda: (
            "X-RateLimit-Limit",
            "RateLimit-Limit",
        )
    )
    retry_after_header_names: Sequence[str] = field(
        default_factory=lambda: ("Retry-After",)
    )

    def __post_init__(self) -> None:
        if self.per_minute_limit is not None and self.per_minute_limit <= 0:
            raise ValueError("per_minute_limit must be positive when provided")
        if self.per_day_limit is not None and self.per_day_limit <= 0:
            raise ValueError("per_day_limit must be positive when provided")
        if not 0 < self.warning_threshold < 1:
            raise ValueError("warning_threshold must be between 0 and 1")
        if not 0 < self.block_threshold <= 1:
            raise ValueError("block_threshold must be between 0 and 1")
        if self.warning_threshold >= self.block_threshold:
            raise ValueError("warning_threshold must be lower than block_threshold")
