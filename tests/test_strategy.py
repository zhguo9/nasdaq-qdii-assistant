from __future__ import annotations

import unittest
from datetime import date, timedelta

from qdii_assistant.models import PortfolioInput, PriceBar, StrategyConfig, TradeFundSnapshot
from qdii_assistant.strategy import build_snapshot, generate_signal


def make_bars(start_price: float, daily_change: float, days: int = 180) -> list[PriceBar]:
    start = date(2026, 1, 1)
    price = start_price
    bars: list[PriceBar] = []
    for i in range(days):
        price *= 1 + daily_change
        bars.append(PriceBar(date=start + timedelta(days=i), close=round(price, 4)))
    return bars


class StrategyTests(unittest.TestCase):
    def test_uptrend_generates_buy_for_cash_portfolio(self) -> None:
        bars = make_bars(100, 0.001)
        signal = generate_signal(
            symbol="^NDX",
            fund_code="161130",
            fund_name="易方达纳斯达克100ETF联接",
            bars=bars,
            portfolio=PortfolioInput(capital=60000, cash=60000, holding_value=0),
            config=StrategyConfig(risk_profile="balanced"),
        )

        self.assertEqual(signal.action, "BUY")
        self.assertGreater(signal.target_allocation, 0.5)
        self.assertEqual(signal.trade_amount_cny, 9000)

    def test_downtrend_reduces_high_position(self) -> None:
        bars = make_bars(200, -0.0015)
        signal = generate_signal(
            symbol="^NDX",
            fund_code="161130",
            fund_name="易方达纳斯达克100ETF联接",
            bars=bars,
            portfolio=PortfolioInput(capital=60000, cash=6000, holding_value=54000),
            config=StrategyConfig(risk_profile="balanced"),
        )

        self.assertEqual(signal.action, "SELL")
        self.assertGreater(signal.trade_amount_cny, 0)
        self.assertLess(signal.target_allocation, signal.current_allocation)

    def test_small_gap_holds(self) -> None:
        bars = make_bars(100, 0.001)
        signal = generate_signal(
            symbol="^NDX",
            fund_code="161130",
            fund_name="易方达纳斯达克100ETF联接",
            bars=bars,
            portfolio=PortfolioInput(capital=60000, cash=12000, holding_value=48000),
            config=StrategyConfig(risk_profile="balanced"),
        )

        self.assertEqual(signal.action, "HOLD")
        self.assertEqual(signal.trade_amount_cny, 0)

    def test_high_premium_blocks_buy(self) -> None:
        bars = make_bars(100, 0.001)
        fund_snapshot = TradeFundSnapshot(
            code="161130",
            name="易方达纳斯达克100ETF联接",
            latest_price=5.30,
            nav=5.00,
            premium_rate=0.06,
            buy_blocked=True,
            warnings=["场内价格相对最新净值溢价超过 5%，本次买入会被过滤为持有。"],
        )

        signal = generate_signal(
            symbol="^NDX",
            fund_code="161130",
            fund_name="易方达纳斯达克100ETF联接",
            bars=bars,
            portfolio=PortfolioInput(capital=60000, cash=60000, holding_value=0),
            config=StrategyConfig(risk_profile="balanced"),
            fund_snapshot=fund_snapshot,
        )

        self.assertEqual(signal.action, "HOLD")
        self.assertEqual(signal.trade_amount_cny, 0)
        self.assertTrue(any("过滤" in reason for reason in signal.reasons))

    def test_snapshot_requires_enough_bars(self) -> None:
        with self.assertRaises(ValueError):
            build_snapshot("^NDX", make_bars(100, 0.001, days=20))


if __name__ == "__main__":
    unittest.main()

