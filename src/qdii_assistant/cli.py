from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .data_provider import MarketDataError, YahooChartProvider, sample_bars
from .journal import append_signal, to_jsonable
from .models import PortfolioInput, StrategyConfig
from .strategy import generate_signal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qdii-assistant",
        description="Generate a compliance-first Nasdaq QDII manual trading decision.",
    )
    parser.add_argument("--symbol", default="QQQ", help="Market proxy symbol, default: QQQ")
    parser.add_argument("--fund-name", default="纳斯达克100 QDII/ETF", help="Actual fund you plan to trade manually")
    parser.add_argument("--capital", type=float, default=60000, help="Planned capital in CNY")
    parser.add_argument("--cash", type=float, default=60000, help="Current cash in CNY")
    parser.add_argument("--holding-value", type=float, default=0, help="Current holding market value in CNY")
    parser.add_argument(
        "--risk-profile",
        choices=["conservative", "balanced", "aggressive"],
        default="balanced",
        help="Risk profile. Default: balanced",
    )
    parser.add_argument("--max-allocation", type=float, default=None, help="Override max allocation, e.g. 0.75")
    parser.add_argument("--range", dest="range_value", default="1y", help="Yahoo chart range, default: 1y")
    parser.add_argument("--record", action="store_true", help="Append this decision to CSV journal")
    parser.add_argument("--journal", default="data/signals.csv", help="CSV journal path")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of human-readable output")
    parser.add_argument("--sample", action="store_true", help="Use built-in sample data without network")
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        bars = sample_bars() if args.sample else YahooChartProvider().fetch_daily_bars(args.symbol, args.range_value)
        signal = generate_signal(
            symbol=args.symbol,
            fund_name=args.fund_name,
            bars=bars,
            portfolio=PortfolioInput(
                capital=args.capital,
                cash=args.cash,
                holding_value=args.holding_value,
            ),
            config=StrategyConfig(
                risk_profile=args.risk_profile,
                max_allocation=args.max_allocation,
            ),
        )
    except (MarketDataError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        if not args.sample:
            print("提示: 可以先运行 `python -m qdii_assistant --sample` 验证程序本身。", file=sys.stderr)
        return 2

    if args.record:
        append_signal(Path(args.journal), signal)

    if args.json:
        print(json.dumps(to_jsonable(signal), ensure_ascii=False, indent=2))
    else:
        print_human(signal, recorded_path=args.journal if args.record else None)

    return 0


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def print_human(signal, recorded_path: str | None = None) -> None:
    snapshot = signal.snapshot
    action_label = {
        "BUY": "买入",
        "SELL": "卖出",
        "HOLD": "持有",
    }.get(signal.action, signal.action)

    print("纳指 QDII 决策助手")
    print("=" * 24)
    print(f"行情代理: {signal.symbol}")
    print(f"手动交易标的: {signal.fund_name}")
    print(f"行情日期: {snapshot.latest_date.isoformat()}")
    print(f"建议动作: {action_label}")
    print(f"目标仓位: {signal.target_allocation:.0%}")
    print(f"当前仓位: {signal.current_allocation:.0%}")
    print(f"本次建议金额: {signal.trade_amount_cny:.0f} 元")
    print(f"单次交易上限: {signal.max_single_trade_cny:.0f} 元")
    print()
    print("市场状态")
    print(f"- 最新收盘: {snapshot.latest_close:.2f}")
    print(f"- MA20 / MA60 / MA120: {snapshot.ma20:.2f} / {snapshot.ma60:.2f} / {snapshot.ma120:.2f}")
    print(f"- 20日动量: {snapshot.momentum20:.1%}")
    print(f"- 近一年高点回撤: {snapshot.drawdown_from_high:.1%}")
    print(f"- 近60日年化波动率: {snapshot.annualized_volatility:.1%}")
    print(f"- 模型分数: {snapshot.score}")
    print()
    print("理由")
    for reason in signal.reasons:
        print(f"- {reason}")
    print()
    print("风险提醒")
    for warning in signal.risk_warnings:
        print(f"- {warning}")
    if recorded_path:
        print()
        print(f"已记录到: {recorded_path}")
