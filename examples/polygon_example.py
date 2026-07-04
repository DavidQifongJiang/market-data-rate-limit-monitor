import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rate_limit_monitor import HttpRateLimitedClient, RateLimitConfig, RateLimitMonitor


def main() -> None:
    api_key = os.getenv("POLYGON_API_KEY") or os.getenv("MASSIVE_API_KEY")
    if not api_key:
        raise SystemExit("Set POLYGON_API_KEY or MASSIVE_API_KEY before running this example.")

    config = RateLimitConfig(
        provider_name="Polygon",
        per_minute_limit=5,
        per_day_limit=500,
    )
    client = HttpRateLimitedClient(RateLimitMonitor(config))

    response = client.get(
        "https://api.polygon.io/v2/aggs/ticker/IBM/range/1/day/2026-06-01/2026-06-05",
        params={
            "adjusted": "true",
            "sort": "asc",
            "apiKey": api_key,
        },
        timeout=15,
    )
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
