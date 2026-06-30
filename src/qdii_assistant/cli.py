from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .data_provider import (
    EastmoneyFundProvider,
    MarketDataError,
    YahooChartProvider,
    sample_bars,
    sample_fund_snapshot,
)
from .journal import append_signal, to_jsonable
from .models import PortfolioInput, StrategyConfig, TradeFundSnapshot
from .strategy import generate_signal


DEFAULT_FUND_CODE = "161130"
DEFAULT_FUND_NAME = "易方达纳斯达克100ETF联接(QDII-LOF)A(人民币)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qdii-assistant",
        description="Generate a compliance-first Nasdaq QDII manual trading decision.",
    )
    parser.add_argument("--symbol", default=None, help="Legacy alias for --signal-symbol")
    parser.add_argument("--signal-symbol", default="^NDX", help="Primary Nasdaq signal symbol, default: ^NDX")
    parser.add_argument("--fallback-symbol", default="QQQ", help="Fallback signal symbol, default: QQQ")
    parser.add_argument("--fund-code", default=DEFAULT_FUND_CODE, help="Actual fund code to check, default: 161130")
    parser.add_argument("--fund-name", default=DEFAULT_FUND_NAME, help="Actual fund name you plan to trade manually")
    parser.add_argument("--fund-market", default="0", choices=["0", "1"], help="Eastmoney market id: 0=SZ, 1=SH")
    parser.add_argument("--skip-fund-check", action="store_true", help="Skip live fund quote/NAV checks")
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
        signal_symbol, bars, data_warnings = load_signal_bars(args)
        fund_snapshot = load_trade_fund(args)
        signal = generate_signal(
            symbol=signal_symbol,
            fund_code=args.fund_code,
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
            fund_snapshot=fund_snapshot,
            data_warnings=data_warnings,
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


def load_signal_bars(args: argparse.Namespace) -> tuple[str, list, list[str]]:
    primary_symbol = args.symbol or args.signal_symbol
    if args.sample:
        return primary_symbol, sample_bars(), ["当前使用样例行情数据，不能用于真实交易。"]

    return YahooChartProvider().fetch_daily_bars_with_fallback(
        primary_symbol=primary_symbol,
        fallback_symbol=args.fallback_symbol,
        range_value=args.range_value,
    )


def load_trade_fund(args: argparse.Namespace) -> TradeFundSnapshot | None:
    if args.skip_fund_check:
        return TradeFundSnapshot(
            code=args.fund_code,
            name=args.fund_name,
            source="skipped",
            warnings=["已跳过实际基金过滤器；下单前必须手动检查折溢价、成交额、限购和暂停申购状态。"],
        )

    if args.sample:
        return sample_fund_snapshot(args.fund_code, args.fund_name)

    try:
        return EastmoneyFundProvider().fetch_fund_snapshot(
            fund_code=args.fund_code,
            market=args.fund_market,
            fallback_name=args.fund_name,
        )
    except MarketDataError as exc:
        return TradeFundSnapshot(
            code=args.fund_code,
            name=args.fund_name,
            source="unavailable",
            warnings=[
                f"{args.fund_code} 实际基金数据获取失败：{exc}",
                "程序仍可给出指数趋势建议，但下单前必须手动检查基金折溢价、成交额、限购和暂停申购状态。",
            ],
        )


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def print_human(signal, recorded_path: str | None = None) -> None:
    snapshot = signal.snapshot
    fund = signal.fund_snapshot
    action_label = {
        "BUY": "买入",
        "SELL": "卖出",
        "HOLD": "持有",
    }.get(signal.action, signal.action)

    print("纳指 QDII 决策助手")
    print("=" * 24)
    print(f"信号指数: {signal.symbol}")
    print(f"手动交易标的: {signal.fund_code} {signal.fund_name}")
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
    print("交易过滤")
    if fund is None:
        print("- 未启用实际基金过滤器")
    else:
        print(f"- 数据来源: {fund.source}")
        print(f"- 场内价格: {format_optional_number(fund.latest_price, '.4f')}")
        print(f"- 最新净值: {format_optional_number(fund.nav, '.4f')}")
        print(f"- 折溢价: {format_optional_percent(fund.premium_rate)}")
        print(f"- 今日成交额: {format_amount(fund.amount_cny)}")
        if fund.price_time:
            print(f"- 价格时间: {fund.price_time.isoformat(timespec='seconds')}")
        if fund.nav_date:
            print(f"- 净值日期: {fund.nav_date.isoformat()}")
        print(f"- 买入过滤: {'触发' if fund.buy_blocked else '未触发'}")
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


def format_optional_number(value: float | None, format_spec: str) -> str:
    if value is None:
        return "未知"
    return format(value, format_spec)


def format_optional_percent(value: float | None) -> str:
    if value is None:
        return "未知"
    return f"{value:.2%}"


def format_amount(value: float | None) -> str:
    if value is None:
        return "未知"
    return f"{value / 10_000:.1f} 万元"
