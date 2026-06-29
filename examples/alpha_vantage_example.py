import os

from rate_limit_monitor import HttpRateLimitedClient, RateLimitConfig, RateLimitMonitor


def main() -> None:
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise SystemExit("Set ALPHA_VANTAGE_API_KEY before running this example.")

    config = RateLimitConfig(
        provider_name="Alpha Vantage",
        per_minute_limit=5,
        per_day_limit=500,
    )
    client = HttpRateLimitedClient(RateLimitMonitor(config))

    response = client.get(
        "https://www.alphavantage.co/query",
        params={
            "function": "TIME_SERIES_DAILY",
            "symbol": "IBM",
            "apikey": api_key,
        },
        timeout=15,
    )
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
