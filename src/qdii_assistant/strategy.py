from __future__ import annotations

import math
import statistics

from .models import (
    DecisionSignal,
    MarketSnapshot,
    PortfolioInput,
    PriceBar,
    StrategyConfig,
    TradeFundSnapshot,
)


def moving_average(values: list[float], window: int) -> float:
    if not values:
        raise ValueError("values cannot be empty")
    actual_window = min(window, len(values))
    return sum(values[-actual_window:]) / actual_window


def annualized_volatility(closes: list[float]) -> float:
    if len(closes) < 22:
        return 0.0

    returns: list[float] = []
    for prev, current in zip(closes, closes[1:]):
        if prev > 0 and current > 0:
            returns.append(math.log(current / prev))

    if len(returns) < 2:
        return 0.0
    return statistics.stdev(returns[-60:]) * math.sqrt(252)


def build_snapshot(symbol: str, bars: list[PriceBar]) -> MarketSnapshot:
    if len(bars) < 60:
        raise ValueError("At least 60 daily bars are required")

    closes = [bar.close for bar in bars]
    latest_close = closes[-1]
    ma20 = moving_average(closes, 20)
    ma60 = moving_average(closes, 60)
    ma120 = moving_average(closes, 120)
    momentum20 = latest_close / closes[-21] - 1 if len(closes) >= 21 else 0.0
    recent_high = max(closes[-252:])
    drawdown = latest_close / recent_high - 1 if recent_high > 0 else 0.0
    volatility = annualized_volatility(closes)

    score = 0
    score += 2 if latest_close > ma120 else -2
    score += 1 if latest_close > ma60 else -1
    score += 1 if ma20 > ma60 else -1
    score += 1 if momentum20 > 0 else -1

    return MarketSnapshot(
        symbol=symbol,
        latest_date=bars[-1].date,
        latest_close=latest_close,
        ma20=ma20,
        ma60=ma60,
        ma120=ma120,
        momentum20=momentum20,
        drawdown_from_high=drawdown,
        annualized_volatility=volatility,
        score=score,
    )


def score_to_allocation(score: int, max_allocation: float) -> float:
    if score >= 4:
        base = 1.00
    elif score >= 2:
        base = 0.75
    elif score >= 0:
        base = 0.50
    elif score >= -2:
        base = 0.25
    else:
        base = 0.00
    return max_allocation * base


def apply_risk_caps(target: float, snapshot: MarketSnapshot) -> tuple[float, list[str]]:
    warnings: list[str] = []
    capped_target = target

    if snapshot.drawdown_from_high <= -0.35:
        capped_target = min(capped_target, 0.20)
        warnings.append("指数距离近一年高点回撤超过 35%，只保留观察仓或小仓位。")
    elif snapshot.drawdown_from_high <= -0.20:
        capped_target = min(capped_target, 0.35)
        warnings.append("指数距离近一年高点回撤超过 20%，仓位上限已降到 35%。")

    if snapshot.annualized_volatility >= 0.40:
        capped_target = min(capped_target, 0.50)
        warnings.append("近 60 日年化波动率高于 40%，避免一次性大额交易。")
    elif snapshot.annualized_volatility >= 0.30:
        capped_target = min(capped_target, 0.65)
        warnings.append("近 60 日年化波动率偏高，本次建议控制节奏。")

    return capped_target, warnings


def round_trade_amount(amount: float, lot: int) -> float:
    if amount <= 0:
        return 0.0
    if lot <= 1:
        return round(amount, 2)
    return float(math.floor(amount / lot) * lot)


def generate_signal(
    symbol: str,
    fund_name: str,
    bars: list[PriceBar],
    portfolio: PortfolioInput,
    config: StrategyConfig,
    fund_code: str = "",
    fund_snapshot: TradeFundSnapshot | None = None,
    data_warnings: list[str] | None = None,
) -> DecisionSignal:
    snapshot = build_snapshot(symbol, bars)
    max_allocation = config.resolved_max_allocation()
    target = score_to_allocation(snapshot.score, max_allocation)
    target, risk_warnings = apply_risk_caps(target, snapshot)

    if portfolio.total_asset <= 0:
        raise ValueError("Total asset must be positive")

    current_allocation = portfolio.current_allocation
    allocation_gap = target - current_allocation
    max_single_trade = portfolio.total_asset * config.max_trade_ratio
    cash_buffer = portfolio.total_asset * config.cash_buffer_ratio
    available_cash = max(0.0, portfolio.cash - cash_buffer)

    action = "HOLD"
    trade_amount = 0.0
    if allocation_gap > config.rebalance_threshold:
        raw_amount = min(allocation_gap * portfolio.total_asset, available_cash, max_single_trade)
        trade_amount = round_trade_amount(raw_amount, config.trade_round_lot_cny)
        action = "BUY" if trade_amount > 0 else "HOLD"
    elif allocation_gap < -config.rebalance_threshold:
        raw_amount = min(abs(allocation_gap) * portfolio.total_asset, portfolio.holding_value, max_single_trade)
        trade_amount = round_trade_amount(raw_amount, config.trade_round_lot_cny)
        action = "SELL" if trade_amount > 0 else "HOLD"

    filter_reasons: list[str] = []
    if action == "BUY" and fund_snapshot and fund_snapshot.buy_blocked:
        action = "HOLD"
        trade_amount = 0.0
        filter_reasons.append(
            f"{fund_snapshot.code} 交易过滤器提示溢价过高，本次把买入建议过滤为持有。"
        )

    reasons = explain(
        snapshot=snapshot,
        current_allocation=current_allocation,
        target=target,
        action=action,
        trade_amount=trade_amount,
        max_allocation=max_allocation,
        allocation_gap=allocation_gap,
        rebalance_threshold=config.rebalance_threshold,
    )
    reasons.extend(describe_fund_filter(fund_snapshot))
    reasons.extend(filter_reasons)

    if data_warnings:
        risk_warnings.extend(data_warnings)
    if fund_snapshot:
        risk_warnings.extend(fund_snapshot.warnings)
    risk_warnings.extend(common_qdii_warnings(action))

    return DecisionSignal(
        symbol=symbol,
        fund_code=fund_code,
        fund_name=fund_name,
        action=action,
        target_allocation=target,
        current_allocation=current_allocation,
        trade_amount_cny=trade_amount,
        total_asset_cny=portfolio.total_asset,
        max_single_trade_cny=max_single_trade,
        snapshot=snapshot,
        fund_snapshot=fund_snapshot,
        reasons=reasons,
        risk_warnings=dedupe(risk_warnings),
    )


def explain(
    snapshot: MarketSnapshot,
    current_allocation: float,
    target: float,
    action: str,
    trade_amount: float,
    max_allocation: float,
    allocation_gap: float,
    rebalance_threshold: float,
) -> list[str]:
    reasons: list[str] = []

    if snapshot.latest_close > snapshot.ma120:
        reasons.append("价格在 120 日均线上方，长期趋势仍偏多。")
    else:
        reasons.append("价格低于 120 日均线，长期趋势偏弱。")

    if snapshot.latest_close > snapshot.ma60:
        reasons.append("价格在 60 日均线上方，中期趋势支持持仓。")
    else:
        reasons.append("价格低于 60 日均线，中期趋势需要谨慎。")

    if snapshot.ma20 > snapshot.ma60:
        reasons.append("20 日均线高于 60 日均线，短中期结构较好。")
    else:
        reasons.append("20 日均线低于 60 日均线，短期结构偏弱。")

    if snapshot.momentum20 > 0:
        reasons.append(f"20 日动量为正，近 20 个交易日上涨 {snapshot.momentum20:.1%}。")
    else:
        reasons.append(f"20 日动量为负，近 20 个交易日下跌 {abs(snapshot.momentum20):.1%}。")

    reasons.append(f"模型分数为 {snapshot.score}，目标仓位为 {target:.0%}，最高允许仓位为 {max_allocation:.0%}。")

    if action == "BUY":
        reasons.append(f"当前仓位 {current_allocation:.0%} 低于目标仓位，建议本次分批买入约 {trade_amount:.0f} 元。")
    elif action == "SELL":
        reasons.append(f"当前仓位 {current_allocation:.0%} 高于目标仓位，建议本次分批卖出约 {trade_amount:.0f} 元。")
    elif allocation_gap > rebalance_threshold:
        reasons.append("当前仓位低于目标仓位，但交易过滤器或现金缓冲使本次暂不买入。")
    elif allocation_gap < -rebalance_threshold:
        reasons.append("当前仓位高于目标仓位，但持仓或交易金额限制使本次暂不卖出。")
    else:
        reasons.append("当前仓位与目标仓位差距不大，建议暂时持有并继续观察。")

    return reasons


def describe_fund_filter(fund_snapshot: TradeFundSnapshot | None) -> list[str]:
    if fund_snapshot is None:
        return ["未启用实际交易基金过滤器；下单前需要手动检查目标基金。"]

    reasons = [f"实际交易标的为 {fund_snapshot.code} {fund_snapshot.name}。"]
    if fund_snapshot.premium_rate is not None:
        reasons.append(f"场内价格相对最新净值折溢价为 {fund_snapshot.premium_rate:.2%}。")
    if fund_snapshot.amount_cny is not None:
        reasons.append(f"今日成交额约 {fund_snapshot.amount_cny / 10_000:.1f} 万元，用于辅助判断流动性。")
    return reasons


def common_qdii_warnings(action: str) -> list[str]:
    warnings = [
        "本工具只生成手动决策参考，不连接券商，不自动下单。",
        "下单前确认实际 QDII/ETF 是否暂停申购、限制申购或存在明显折溢价。",
    ]
    if action == "BUY":
        warnings.append("买入前确认本次金额不会影响生活备用金。")
    return warnings


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

