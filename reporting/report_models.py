# -*- coding: utf-8 -*-
"""
reporting/report_models.py
──────────────────────────
Pure data contracts for the reporting layer.

No Streamlit. No app imports. No side effects.
These dataclasses define exactly what each report section expects as input.
The rest of the app is responsible for filling them from its own data structures.

Typical usage:
    from reporting.report_models import PortfolioReportInput, OptimizerReportInput
    from reporting.report_builder import build_portfolio_report, build_optimizer_report

    data = PortfolioReportInput(
        client_name="ישראל ישראלי",
        holdings_df=df,
        totals=totals,
        ...
    )
    report_bytes = build_portfolio_report(data)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


# ── Portfolio snapshot / comparison models ────────────────────────────────────

@dataclass
class PortfolioSnapshot:
    """A point-in-time summary of a portfolio's key metrics.

    Allocation values are percentages (0–100).
    Use float('nan') for unknown/unavailable values.

    Example
    ───────
    current = PortfolioSnapshot(
        total_value=1_500_000,
        allocations={"equities": 40.0, "abroad": 30.0, "fx": 25.0, "illiquid": 20.0},
        sharpe=0.82,
        cost=0.45,
        managers_count=3,
        products_count=5,
    )
    """
    total_value:     float
    allocations:     dict = field(default_factory=dict)
    # allocations keys: "equities", "abroad", "fx", "illiquid"
    # values are percentages (0–100); use float('nan') for unknown
    sharpe:          float = float("nan")
    cost:            float = float("nan")   # annual cost %
    managers_count:  int   = 0
    products_count:  int   = 0

    def is_valid(self) -> bool:
        return self.total_value > 0

    def allocation(self, key: str) -> float:
        """Return an allocation value by key, or nan if absent."""
        return self.allocations.get(key, float("nan"))


@dataclass
class PortfolioAction:
    """A single recommended action in a portfolio transition plan.

    action_type  : "replace" | "add" | "remove"
    original_product : name of the product being replaced/removed (empty for "add")
    new_product  : name of the product being added/introduced (empty for "remove")
    manager      : the investment manager name
    impact_summary : free-text description of the expected impact

    Example
    ───────
    action = PortfolioAction(
        action_type="replace",
        original_product="קרן השתלמות הראל מסלול כללי",
        new_product="קרן השתלמות מגדל מסלול מניות",
        manager="מגדל",
        impact_summary="הגדלת חשיפה למניות ב-15pp, שיפור שארפ צפוי +0.12",
    )
    """
    action_type:      str   # "replace" | "add" | "remove"
    manager:          str   = ""
    original_product: str   = ""
    new_product:      str   = ""
    impact_summary:   str   = ""

    def validate(self) -> list[str]:
        warnings = []
        if self.action_type not in ("replace", "add", "remove"):
            warnings.append(f"action_type לא חוקי: '{self.action_type}'. חייב להיות replace / add / remove")
        if self.action_type == "replace" and not self.original_product:
            warnings.append("replace חייב לכלול original_product")
        if self.action_type in ("replace", "add") and not self.new_product:
            warnings.append(f"{self.action_type} חייב לכלול new_product")
        if self.action_type == "remove" and not self.original_product:
            warnings.append("remove חייב לכלול original_product")
        return warnings


@dataclass
class PortfolioComparison:
    """Side-by-side comparison between a current and a proposed portfolio.

    delta_allocations mirrors the allocations dict keys ("equities", "abroad", etc.)
    and holds the signed difference (proposed − current) in percentage points.

    Example
    ───────
    comparison = PortfolioComparison(
        current_snapshot=current,
        proposed_snapshot=proposed,
        delta_allocations={"equities": +5.0, "abroad": -3.0, "fx": 0.0, "illiquid": -2.0},
        delta_sharpe=+0.08,
        delta_cost=-0.05,
    )
    """
    current_snapshot:  PortfolioSnapshot
    proposed_snapshot: PortfolioSnapshot
    delta_allocations: dict = field(default_factory=dict)
    # keys match allocations keys; values are signed pp differences
    delta_sharpe:      float = float("nan")
    delta_cost:        float = float("nan")

    @classmethod
    def from_snapshots(
        cls,
        current: PortfolioSnapshot,
        proposed: PortfolioSnapshot,
    ) -> "PortfolioComparison":
        """Convenience constructor: auto-compute deltas from two snapshots."""
        all_keys = set(current.allocations) | set(proposed.allocations)
        deltas = {
            k: proposed.allocation(k) - current.allocation(k)
            for k in all_keys
            if not (math.isnan(proposed.allocation(k)) or math.isnan(current.allocation(k)))
        }
        ds = (
            proposed.sharpe - current.sharpe
            if not (math.isnan(proposed.sharpe) or math.isnan(current.sharpe))
            else float("nan")
        )
        dc = (
            proposed.cost - current.cost
            if not (math.isnan(proposed.cost) or math.isnan(current.cost))
            else float("nan")
        )
        return cls(
            current_snapshot=current,
            proposed_snapshot=proposed,
            delta_allocations=deltas,
            delta_sharpe=ds,
            delta_cost=dc,
        )

    def validate(self) -> list[str]:
        warnings = []
        if not self.current_snapshot.is_valid():
            warnings.append("current_snapshot אינו תקין (total_value <= 0)")
        if not self.proposed_snapshot.is_valid():
            warnings.append("proposed_snapshot אינו תקין (total_value <= 0)")
        return warnings



# ── Portfolio / Client Report ─────────────────────────────────────────────────

@dataclass
class PortfolioReportInput:
    """
    All data needed to produce a client-portfolio summary report.
    Pass only plain Python objects / DataFrames — no Streamlit state.

    Required
    ────────
    holdings_df   : DataFrame with columns:
                    provider, product_name, track, product_type,
                    amount, equity_pct, foreign_pct, fx_pct, illiquid_pct
                    (nan allowed for allocation columns)
    totals        : dict from client_portfolio.charts.compute_totals()
                    keys: total, n_products, n_managers,
                          equity, foreign, fx, illiquid, cost

    Optional
    ────────
    client_name   : shown in the report header
    report_date   : ISO date string e.g. "2025-01"  (defaults to today)
    product_type  : active product tab label (e.g. "קרנות השתלמות")
    cost_df       : DataFrame with annual_cost_pct per row (for cost section)
    ai_commentary : free-text AI-generated analysis to embed in the report
    """
    holdings_df:   pd.DataFrame
    totals:        dict

    client_name:   str                    = "לקוח"
    report_date:   str                    = ""
    product_type:  str                    = ""
    cost_df:       Optional[pd.DataFrame] = None
    ai_commentary: str                    = ""

    def validate(self) -> list[str]:
        """Return a list of validation warnings (empty = OK)."""
        warnings: list[str] = []
        required_cols = {"provider", "product_name", "amount"}
        missing = required_cols - set(self.holdings_df.columns)
        if missing:
            warnings.append(f"holdings_df חסרות עמודות: {missing}")
        if self.holdings_df.empty:
            warnings.append("holdings_df ריק — אין מוצרים לדיווח")
        if not isinstance(self.totals, dict):
            warnings.append("totals חייב להיות dict")
        return warnings


# ── Optimizer Report ──────────────────────────────────────────────────────────

@dataclass
class OptimizerAlternative:
    """A single optimizer recommendation."""
    label:       str          # e.g. "חלופה משוקללת"
    managers:    str          # pipe-separated manager names
    funds:       str          # pipe-separated fund names
    tracks:      str          # pipe-separated track names
    weights:     tuple        # e.g. (60, 40)
    foreign_pct: float = math.nan
    stocks_pct:  float = math.nan
    fx_pct:      float = math.nan
    illiquid_pct: float = math.nan
    sharpe:      float = math.nan
    service:     float = math.nan
    score:       float = math.nan
    advantage:   str   = ""
    ai_text:     str   = ""


@dataclass
class OptimizerReportInput:
    """
    All data needed to produce an optimizer results report.

    Required
    ────────
    alternatives  : list of OptimizerAlternative (1–4 items)
    targets       : dict of user targets, e.g.
                    {"foreign": 30.0, "stocks": 40.0, "fx": 25.0, "illiquid": 20.0}

    Optional
    ────────
    client_name   : shown in the report header
    report_date   : ISO date string
    product_type  : active product tab label
    baseline      : dict of current-portfolio exposures (same keys as targets)
    primary_rank  : "דיוק" | "שארפ" | "שירות ואיכות"
    """
    alternatives: list[OptimizerAlternative]
    targets:      dict

    client_name:  str               = "לקוח"
    report_date:  str               = ""
    product_type: str               = ""
    baseline:     Optional[dict]    = None
    primary_rank: str               = "דיוק"

    def validate(self) -> list[str]:
        warnings: list[str] = []
        if not self.alternatives:
            warnings.append("אין חלופות לדיווח")
        if not isinstance(self.targets, dict):
            warnings.append("targets חייב להיות dict")
        return warnings


# ── ISA / Institutional Strategy Report ──────────────────────────────────────

@dataclass
class ISAReportInput:
    """
    Data for an institutional-strategy analysis report.

    Required
    ────────
    display_df    : the filtered time-series DataFrame used for charts.
                    columns: manager, track, date, allocation_name, allocation_value
    managers      : list of manager names included in the analysis
    tracks        : list of track names
    allocation_names : list of allocation component names

    Optional
    ────────
    product_type  : active product tab label
    date_range    : e.g. "2020-01 – 2025-01"
    ai_sections   : dict of section_title → section_text (from AnalysisResult.sections)
    report_date   : ISO date string
    """
    display_df:       pd.DataFrame
    managers:         list[str]
    tracks:           list[str]
    allocation_names: list[str]

    product_type:  str        = ""
    date_range:    str        = ""
    ai_sections:   dict       = field(default_factory=dict)
    report_date:   str        = ""

    def validate(self) -> list[str]:
        warnings: list[str] = []
        required_cols = {"manager", "track", "date", "allocation_name", "allocation_value"}
        missing = required_cols - set(self.display_df.columns)
        if missing:
            warnings.append(f"display_df חסרות עמודות: {missing}")
        if self.display_df.empty:
            warnings.append("display_df ריק — אין נתונים לדיווח")
        return warnings
