from __future__ import annotations

import unittest
from datetime import date, timedelta

from qdii_assistant.models import PortfolioInput, PriceBar, StrategyConfig
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
            symbol="QQQ",
            fund_name="纳斯达克100 QDII",
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
            symbol="QQQ",
            fund_name="纳斯达克100 QDII",
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
            symbol="QQQ",
            fund_name="纳斯达克100 QDII",
            bars=bars,
            portfolio=PortfolioInput(capital=60000, cash=12000, holding_value=48000),
            config=StrategyConfig(risk_profile="balanced"),
        )

        self.assertEqual(signal.action, "HOLD")
        self.assertEqual(signal.trade_amount_cny, 0)

    def test_snapshot_requires_enough_bars(self) -> None:
        with self.assertRaises(ValueError):
            build_snapshot("QQQ", make_bars(100, 0.001, days=20))


if __name__ == "__main__":
    unittest.main()

