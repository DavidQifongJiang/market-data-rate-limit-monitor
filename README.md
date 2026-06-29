# market-data-rate-limit-monitor

A small, API-agnostic Python package for monitoring market-data API rate limits.
It works with providers such as Alpha Vantage, Yahoo Finance, Polygon, or any
HTTP API that exposes quota headers or fixed usage limits.

## Features

- Per-minute and per-day request tracking.
- Configurable provider limits.
- Python logging warning at 80% usage.
- `RateLimitExceededError` blocking at 95% usage.
- Configurable response-header quota detection.
- Internal counter fallback when headers are missing.
- Thin `requests` wrapper that calls `before_request()` and `after_response()`.

## Install

```bash
pip install -r requirements.txt
pip install -e .
```

## Test

```bash
python -m unittest discover -s tests
```

Tests use mocks only and do not require real API keys.

## Usage

```python
from rate_limit_monitor import HttpRateLimitedClient, RateLimitConfig, RateLimitMonitor

config = RateLimitConfig(
    provider_name="Example Provider",
    per_minute_limit=60,
    per_day_limit=5000,
)

monitor = RateLimitMonitor(config)
client = HttpRateLimitedClient(monitor)

response = client.get("https://api.example.com/market-data")
data = response.json()
```

The monitor keeps UTC minute/day counters. It logs once a window reaches 80% of a
configured limit and blocks further requests once usage reaches 95%. If response
headers are present, it derives provider-reported usage from `limit - remaining`.
If headers are missing, it uses internal counters.

Default header names include `X-RateLimit-Remaining`, `X-RateLimit-Limit`,
`RateLimit-Remaining`, `RateLimit-Limit`, and `Retry-After`.

## Alpha Vantage Example

```bash
set ALPHA_VANTAGE_API_KEY=your_api_key_here
python -m examples.alpha_vantage_example
```

On macOS/Linux:

```bash
export ALPHA_VANTAGE_API_KEY=your_api_key_here
python -m examples.alpha_vantage_example
```

The example uses Alpha Vantage's public market-data endpoint and common free-tier
style limits: 5 requests per minute and 500 requests per day.
