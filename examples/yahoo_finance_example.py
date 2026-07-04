import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rate_limit_monitor import HttpRateLimitedClient, RateLimitConfig, RateLimitMonitor


def main() -> None:
    config = RateLimitConfig(
        provider_name="Yahoo Finance",
        per_minute_limit=60,
        per_day_limit=2000,
    )
    monitor = RateLimitMonitor(config)
    client = HttpRateLimitedClient(monitor)

    response = client.get(
        "https://query1.finance.yahoo.com/v8/finance/chart/IBM",
        params={
            "range": "5d",
            "interval": "1d",
        },
        headers={"User-Agent": "market-data-rate-limit-monitor/0.1"},
        timeout=15,
    )
    if response.status_code == 429:
        raise SystemExit("Yahoo Finance returned HTTP 429. Try again after the provider resets.")
    response.raise_for_status()
    payload = response.json()
    result = payload["chart"]["result"][0]

    print(
        {
            "symbol": result["meta"]["symbol"],
            "currency": result["meta"].get("currency"),
            "points": len(result.get("timestamp", [])),
            "usage": monitor.usage_snapshot(),
        }
    )


if __name__ == "__main__":
    main()
