from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from qdii_assistant.data_provider import sample_bars
from qdii_assistant.journal import append_signal
from qdii_assistant.models import PortfolioInput, StrategyConfig
from qdii_assistant.strategy import generate_signal


class JournalTests(unittest.TestCase):
    def test_append_signal_writes_header_and_row(self) -> None:
        signal = generate_signal(
            symbol="QQQ",
            fund_name="纳斯达克100 QDII",
            bars=sample_bars(),
            portfolio=PortfolioInput(capital=60000, cash=60000, holding_value=0),
            config=StrategyConfig(),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "signals.csv"
            append_signal(path, signal)

            with path.open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "QQQ")
        self.assertIn(rows[0]["action"], {"BUY", "SELL", "HOLD"})


if __name__ == "__main__":
    unittest.main()

