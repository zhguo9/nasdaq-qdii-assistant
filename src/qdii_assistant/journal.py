from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from .models import DecisionSignal


CSV_FIELDS = [
    "date",
    "signal_symbol",
    "fund_code",
    "fund_name",
    "action",
    "target_allocation",
    "current_allocation",
    "trade_amount_cny",
    "total_asset_cny",
    "latest_close",
    "ma20",
    "ma60",
    "ma120",
    "momentum20",
    "drawdown_from_high",
    "annualized_volatility",
    "score",
    "fund_price",
    "fund_nav",
    "fund_premium_rate",
    "fund_amount_cny",
    "fund_price_time",
    "fund_nav_date",
    "reasons",
    "risk_warnings",
]


def signal_to_dict(signal: DecisionSignal) -> dict[str, object]:
    snapshot = signal.snapshot
    fund = signal.fund_snapshot
    return {
        "date": snapshot.latest_date.isoformat(),
        "signal_symbol": signal.symbol,
        "fund_code": signal.fund_code,
        "fund_name": signal.fund_name,
        "action": signal.action,
        "target_allocation": round(signal.target_allocation, 4),
        "current_allocation": round(signal.current_allocation, 4),
        "trade_amount_cny": round(signal.trade_amount_cny, 2),
        "total_asset_cny": round(signal.total_asset_cny, 2),
        "latest_close": round(snapshot.latest_close, 4),
        "ma20": round(snapshot.ma20, 4),
        "ma60": round(snapshot.ma60, 4),
        "ma120": round(snapshot.ma120, 4),
        "momentum20": round(snapshot.momentum20, 4),
        "drawdown_from_high": round(snapshot.drawdown_from_high, 4),
        "annualized_volatility": round(snapshot.annualized_volatility, 4),
        "score": snapshot.score,
        "fund_price": round(fund.latest_price, 4) if fund and fund.latest_price is not None else "",
        "fund_nav": round(fund.nav, 4) if fund and fund.nav is not None else "",
        "fund_premium_rate": round(fund.premium_rate, 4) if fund and fund.premium_rate is not None else "",
        "fund_amount_cny": round(fund.amount_cny, 2) if fund and fund.amount_cny is not None else "",
        "fund_price_time": fund.price_time.isoformat(timespec="seconds") if fund and fund.price_time else "",
        "fund_nav_date": fund.nav_date.isoformat() if fund and fund.nav_date else "",
        "reasons": json.dumps(signal.reasons, ensure_ascii=False),
        "risk_warnings": json.dumps(signal.risk_warnings, ensure_ascii=False),
    }


def append_signal(path: str | Path, signal: DecisionSignal) -> None:
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    row = signal_to_dict(signal)
    should_write_header = not csv_path.exists() or csv_path.stat().st_size == 0

    with csv_path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        if should_write_header:
            writer.writeheader()
        writer.writerow(row)


def to_jsonable(signal: DecisionSignal) -> dict[str, object]:
    value = asdict(signal)
    return convert_dates(value)


def convert_dates(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [convert_dates(item) for item in value]
    if isinstance(value, dict):
        return {key: convert_dates(item) for key, item in value.items()}
    return value

