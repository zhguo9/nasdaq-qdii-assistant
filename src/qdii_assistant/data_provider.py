from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .models import PriceBar, TradeFundSnapshot


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
        payload = self._get_json(url)

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

    def fetch_daily_bars_with_fallback(
        self,
        primary_symbol: str,
        fallback_symbol: str | None,
        range_value: str = "1y",
        interval: str = "1d",
    ) -> tuple[str, list[PriceBar], list[str]]:
        warnings: list[str] = []
        try:
            return primary_symbol, self.fetch_daily_bars(primary_symbol, range_value, interval), warnings
        except MarketDataError as exc:
            if not fallback_symbol:
                raise
            warnings.append(f"{primary_symbol} 行情获取失败，已改用 {fallback_symbol} 作为备用信号源：{exc}")

        return fallback_symbol, self.fetch_daily_bars(fallback_symbol, range_value, interval), warnings

    def _get_json(self, url: str) -> dict[str, object]:
        request = Request(url, headers=default_headers("application/json"))
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise MarketDataError(f"Could not load market data: {exc}") from exc


class EastmoneyFundProvider:
    def __init__(self, timeout_seconds: int = 15) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_fund_snapshot(
        self,
        fund_code: str,
        market: str = "0",
        fallback_name: str | None = None,
    ) -> TradeFundSnapshot:
        warnings: list[str] = []
        quote = self._fetch_exchange_quote(fund_code, market)

        nav: float | None = None
        nav_date: date | None = None
        nav_name: str | None = None
        try:
            nav, nav_date, nav_name = self._fetch_latest_nav(fund_code)
        except MarketDataError as exc:
            warnings.append(f"未能获取 {fund_code} 最新净值，无法自动计算折溢价：{exc}")

        name = quote.get("name") or nav_name or fallback_name or fund_code
        price = quote.get("latest_price")
        premium_rate = (price / nav - 1) if price is not None and nav and nav > 0 else None
        buy_blocked = False

        if premium_rate is None:
            warnings.append("无法计算场内价格相对净值的折溢价，买入前需要手动检查。")
        elif premium_rate >= 0.05:
            buy_blocked = True
            warnings.append("场内价格相对最新净值溢价超过 5%，本次买入会被过滤为持有。")
        elif premium_rate >= 0.02:
            warnings.append("场内价格相对最新净值溢价超过 2%，买入前要确认溢价可接受。")
        elif premium_rate <= -0.05:
            warnings.append("场内价格相对最新净值折价超过 5%，卖出前注意成交价格可能偏低。")

        amount_cny = quote.get("amount_cny")
        if amount_cny is not None and amount_cny < 2_000_000:
            warnings.append("今日成交额低于 200 万元，流动性偏弱，建议用限价单和更小金额。")

        if nav_date is not None and (date.today() - nav_date).days >= 5:
            warnings.append("最新净值日期距离今天已达到 5 天或更久，QDII 净值可能明显滞后。")

        warnings.append("程序无法判断申购额度、暂停申购、限购状态；下单前仍需在广发页面确认。")

        return TradeFundSnapshot(
            code=fund_code,
            name=name,
            market=market,
            latest_price=price,
            previous_close=quote.get("previous_close"),
            pct_change=quote.get("pct_change"),
            amount_cny=amount_cny,
            price_time=quote.get("price_time"),
            nav=nav,
            nav_date=nav_date,
            premium_rate=premium_rate,
            source="eastmoney",
            buy_blocked=buy_blocked,
            warnings=warnings,
        )

    def _fetch_exchange_quote(self, fund_code: str, market: str) -> dict[str, object]:
        fields = "f43,f47,f48,f57,f58,f60,f86,f169,f170"
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={market}.{fund_code}&fields={fields}"
        payload = self._get_json(url)
        data = payload.get("data")
        if not isinstance(data, dict):
            raise MarketDataError(f"Unexpected Eastmoney quote response for {fund_code}")

        latest_price = scaled_price(data.get("f43"))
        if latest_price is None:
            raise MarketDataError(f"No valid exchange price returned for {fund_code}")

        price_time = None
        timestamp = as_float(data.get("f86"))
        if timestamp:
            price_time = datetime.fromtimestamp(timestamp)

        return {
            "code": str(data.get("f57") or fund_code),
            "name": str(data.get("f58") or fund_code),
            "latest_price": latest_price,
            "previous_close": scaled_price(data.get("f60")),
            "pct_change": percent_from_eastmoney(data.get("f170")),
            "amount_cny": as_float(data.get("f48")),
            "price_time": price_time,
        }

    def _fetch_latest_nav(self, fund_code: str) -> tuple[float, date | None, str | None]:
        url = f"https://fund.eastmoney.com/pingzhongdata/{fund_code}.js"
        text = self._get_text(url)

        name = None
        name_match = re.search(r'var\s+fS_name\s*=\s*"([^"]+)"', text)
        if name_match:
            name = name_match.group(1)

        trend_match = re.search(r"var\s+Data_netWorthTrend\s*=\s*(\[.*?\]);", text, re.S)
        if not trend_match:
            raise MarketDataError("Data_netWorthTrend was not found")

        try:
            values = json.loads(trend_match.group(1))
        except json.JSONDecodeError as exc:
            raise MarketDataError("Data_netWorthTrend could not be parsed") from exc

        points: list[tuple[int, float]] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            timestamp = item.get("x")
            nav = item.get("y")
            if timestamp is None or nav is None:
                continue
            points.append((int(timestamp), float(nav)))

        if not points:
            raise MarketDataError("No net-worth points were returned")

        latest_timestamp, latest_nav = max(points, key=lambda value: value[0])
        latest_date = datetime.fromtimestamp(latest_timestamp / 1000, tz=timezone.utc).date()
        return latest_nav, latest_date, name

    def _get_json(self, url: str) -> dict[str, object]:
        request = Request(url, headers=default_headers("application/json"))
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise MarketDataError(f"Could not load Eastmoney JSON: {exc}") from exc

    def _get_text(self, url: str) -> str:
        request = Request(url, headers=default_headers("*/*"))
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read().decode("utf-8-sig")
        except (HTTPError, URLError, TimeoutError, UnicodeDecodeError) as exc:
            raise MarketDataError(f"Could not load Eastmoney fund page data: {exc}") from exc


def default_headers(accept: str) -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0 Safari/537.36"
        ),
        "Accept": accept,
    }


def scaled_price(value: object) -> float | None:
    number = as_float(value)
    if number is None:
        return None
    return number / 1000 if abs(number) >= 100 else number


def percent_from_eastmoney(value: object) -> float | None:
    number = as_float(value)
    if number is None:
        return None
    return number / 100


def as_float(value: object) -> float | None:
    if value is None or value == "-":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def sample_bars(days: int = 180) -> list[PriceBar]:
    start = date.today() - timedelta(days=days)
    bars: list[PriceBar] = []
    price = 100.0
    for i in range(days):
        # A gentle uptrend with cyclical noise. This is for demos and tests only.
        price *= 1.0009 + math.sin(i / 9.0) * 0.002
        bars.append(PriceBar(date=start + timedelta(days=i), close=round(price, 2)))
    return bars


def sample_fund_snapshot(
    fund_code: str = "161130",
    fund_name: str = "易方达纳斯达克100ETF联接(QDII-LOF)A(人民币)",
) -> TradeFundSnapshot:
    latest_price = 4.67
    nav = 4.62
    return TradeFundSnapshot(
        code=fund_code,
        name=fund_name,
        latest_price=latest_price,
        previous_close=4.62,
        pct_change=1.08,
        amount_cny=10_000_000,
        price_time=datetime.now(),
        nav=nav,
        nav_date=date.today() - timedelta(days=1),
        premium_rate=latest_price / nav - 1,
        source="sample",
        warnings=["样例基金数据仅用于验证程序流程，不能用于真实下单。"],
    )
