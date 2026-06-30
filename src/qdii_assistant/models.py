from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


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
class TradeFundSnapshot:
    code: str
    name: str
    market: str = "0"
    latest_price: float | None = None
    previous_close: float | None = None
    pct_change: float | None = None
    amount_cny: float | None = None
    price_time: datetime | None = None
    nav: float | None = None
    nav_date: date | None = None
    premium_rate: float | None = None
    source: str = "unavailable"
    buy_blocked: bool = False
    warnings: list[str] = field(default_factory=list)


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
    fund_code: str = ""
    fund_snapshot: TradeFundSnapshot | None = None
    reasons: list[str] = field(default_factory=list)
    risk_warnings: list[str] = field(default_factory=list)

