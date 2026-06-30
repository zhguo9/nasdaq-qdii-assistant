from __future__ import annotations

import json
import math
from datetime import date, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import PriceBar


class MarketDataError(RuntimeError):
    """Raised when remote market data cannot be loaded or parsed."""


class YahooChartProvider:
    def __init__(self, timeout_seconds: int = 15) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_daily_bars(
        self,
        symbol: str,
        range_value: str = "1y",
        interval: str = "1d",
    ) -> list[PriceBar]:
        encoded_symbol = quote(symbol, safe="")
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}"
            f"?range={range_value}&interval={interval}"
        )
        request = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise MarketDataError(f"Could not load Yahoo chart data for {symbol}: {exc}") from exc

        try:
            result = payload["chart"]["result"][0]
            timestamps = result["timestamp"]
            closes = result["indicators"]["quote"][0]["close"]
        except (KeyError, IndexError, TypeError) as exc:
            raise MarketDataError(f"Unexpected Yahoo chart response for {symbol}") from exc

        bars: list[PriceBar] = []
        for timestamp, close in zip(timestamps, closes):
            if close is None or not math.isfinite(float(close)):
                continue
            bars.append(PriceBar(date=date.fromtimestamp(timestamp), close=float(close)))

        if len(bars) < 60:
            raise MarketDataError(f"Only {len(bars)} valid bars were returned for {symbol}")

        return bars


def sample_bars(days: int = 180) -> list[PriceBar]:
    start = date.today() - timedelta(days=days)
    bars: list[PriceBar] = []
    price = 100.0
    for i in range(days):
        # A gentle uptrend with cyclical noise. This is for demos and tests only.
        price *= 1.0009 + math.sin(i / 9.0) * 0.002
        bars.append(PriceBar(date=start + timedelta(days=i), close=round(price, 2)))
    return bars

