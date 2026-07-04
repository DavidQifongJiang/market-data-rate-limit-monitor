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

## Rate-Limit Algorithm

This project uses a fixed window counter algorithm. The monitor keeps separate
UTC counters for the active minute and active day, increments both counters
before each allowed request, and resets them when their time window changes.

This design was chosen because the target public market data APIs commonly
publish simple per-minute and per-day quotas. Fixed window counters are simple,
transparent, easy to test, and directly match the requirement to track request
volume per minute and per day. Token bucket, leaky bucket, and sliding-window
approaches are useful for smoother or more precise rolling-window enforcement,
but they add complexity that is not needed for these published quota windows.

Common rate-limit algorithm tradeoffs:

- Token bucket: allows short bursts while enforcing an average request rate, but
  needs token refill logic and does not directly model daily quotas on its own.
- Leaky bucket: smooths traffic into a steady output rate, but can delay
  requests and is less natural for simple per-minute/per-day published quotas.
- Fixed window counter: simple, low-memory, easy to test, and directly matches
  per-minute/per-day limits, but can allow bursts around window boundaries.
- Sliding window log: very accurate for rolling windows because it stores each
  request timestamp, but uses more memory and cleanup logic.
- Sliding window counter: smoother than fixed windows and cheaper than a full
  log, but it is approximate and more complex to explain and test.

## Alpha Vantage Example

PowerShell:

```powershell
$env:ALPHA_VANTAGE_API_KEY="your_api_key_here"
python examples/alpha_vantage_example.py
```

On macOS/Linux:

```bash
export ALPHA_VANTAGE_API_KEY=your_api_key_here
python examples/alpha_vantage_example.py
```

The example uses Alpha Vantage's public market-data endpoint and common free-tier
style limits: 5 requests per minute and 500 requests per day.

## Polygon Example

PowerShell:

```powershell
$env:POLYGON_API_KEY="your_api_key_here"
python examples/polygon_example.py
```

You can also use `MASSIVE_API_KEY` for the same example if your account labels
the key that way. The API key is read from the environment and is never stored in
source code.

## Yahoo Finance Example

Yahoo Finance does not require an API key for this example:

```bash
python examples/yahoo_finance_example.py
```

The Yahoo example uses Yahoo's public chart endpoint through
`HttpRateLimitedClient`. Because Yahoo does not expose quota headers for this
request in the same way some API products do, the example uses the monitor's
internal counters.
