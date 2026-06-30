from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class PriceBar:
    date: date
    close: float


@dataclass(frozen=True)
class PortfolioInput:
    capital: float
    cash: float
    holding_value: float

    @property
    def total_asset(self) -> float:
        return self.cash + self.holding_value

    @property
    def current_allocation(self) -> float:
        if self.total_asset <= 0:
            return 0.0
        return self.holding_value / self.total_asset


@dataclass(frozen=True)
class StrategyConfig:
    risk_profile: str = "balanced"
    max_allocation: float | None = None
    rebalance_threshold: float = 0.05
    max_trade_ratio: float = 0.15
    cash_buffer_ratio: float = 0.05
    trade_round_lot_cny: int = 100

    def resolved_max_allocation(self) -> float:
        if self.max_allocation is not None:
            return max(0.0, min(1.0, self.max_allocation))

        profile_max = {
            "conservative": 0.60,
            "balanced": 0.80,
            "aggressive": 0.95,
        }
        return profile_max.get(self.risk_profile, 0.80)


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    latest_date: date
    latest_close: float
    ma20: float
    ma60: float
    ma120: float
    momentum20: float
    drawdown_from_high: float
    annualized_volatility: float
    score: int


@dataclass(frozen=True)
class DecisionSignal:
    symbol: str
    fund_name: str
    action: str
    target_allocation: float
    current_allocation: float
    trade_amount_cny: float
    total_asset_cny: float
    max_single_trade_cny: float
    snapshot: MarketSnapshot
    reasons: list[str] = field(default_factory=list)
    risk_warnings: list[str] = field(default_factory=list)

