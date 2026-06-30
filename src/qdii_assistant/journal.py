from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

from .models import DecisionSignal


CSV_FIELDS = [
    "date",
    "symbol",
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
    "reasons",
    "risk_warnings",
]


def signal_to_dict(signal: DecisionSignal) -> dict[str, object]:
    snapshot = signal.snapshot
    return {
        "date": snapshot.latest_date.isoformat(),
        "symbol": signal.symbol,
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
    value["snapshot"]["latest_date"] = signal.snapshot.latest_date.isoformat()
    return value

