# -*- coding: utf-8 -*-
"""
case_management/__init__.py  ·  Phase 3
Single source of truth for one client advisory engagement.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

# ── Workflow step constants ────────────────────────────────────────────────────
STEP_CASE_SETUP    = 1
STEP_DATA_INTAKE   = 2
STEP_SNAPSHOT      = 3
STEP_OPTIMIZATION  = 4
STEP_AI_REVIEW     = 5
STEP_BEFORE_AFTER  = 6
STEP_EXPORT        = 7

STEP_LABELS = {
    STEP_CASE_SETUP:   "פתיחת תיק",
    STEP_DATA_INTAKE:  "קליטת נתונים",
    STEP_SNAPSHOT:     "תמונת מצב",
    STEP_OPTIMIZATION: "אופטימיזציה",
    STEP_AI_REVIEW:    "הסברי AI",
    STEP_BEFORE_AFTER: "לפני / אחרי",
    STEP_EXPORT:       "ייצוא",
}
STEP_ICONS = {1:"📁",2:"📥",3:"📊",4:"🎯",5:"🤖",6:"⚖️",7:"📋"}


# ── Sub-objects ───────────────────────────────────────────────────────────────

@dataclass
class PortfolioSnapshot:
    """Weighted summary of a portfolio at a point in time."""
    total_value:      float = 0.0
    n_products:       int   = 0
    n_managers:       int   = 0
    stocks_pct:       float = math.nan
    foreign_pct:      float = math.nan
    fx_pct:           float = math.nan
    illiquid_pct:     float = math.nan
    sharpe:           float = math.nan
    cost_pct:         float = math.nan
    manager_breakdown: Dict[str, float] = field(default_factory=dict)
    raw: Dict = field(default_factory=dict)  # original baseline dict for engine compatibility

    @classmethod
    def from_baseline_dict(cls, d: dict, total: float = 0.0) -> "PortfolioSnapshot":
        """Build from the existing 'portfolio_baseline' session_state format."""
        if not d:
            return cls()
        def _f(v):
            try: return float(v) if v is not None else math.nan
            except: return math.nan
        return cls(
            total_value  = float(total or d.get("amount", 0) or 0),
            stocks_pct   = _f(d.get("stocks")),
            foreign_pct  = _f(d.get("foreign")),
            fx_pct       = _f(d.get("fx")),
            illiquid_pct = _f(d.get("illiquid")),
            sharpe       = _f(d.get("sharpe")),
            cost_pct     = _f(d.get("service")),
            raw          = dict(d),
        )

    def to_dict(self) -> dict:
        return {
            "total_value": self.total_value, "n_products": self.n_products,
            "n_managers": self.n_managers, "stocks_pct": self.stocks_pct,
            "foreign_pct": self.foreign_pct, "fx_pct": self.fx_pct,
            "illiquid_pct": self.illiquid_pct, "sharpe": self.sharpe,
            "cost_pct": self.cost_pct, "raw": self.raw,
        }


@dataclass
class ExposureDelta:
    """Before/after delta for one exposure metric."""
    metric:     str   = ""
    label_he:   str   = ""
    before:     Optional[float] = None
    after:      Optional[float] = None
    delta_pp:   Optional[float] = None
    direction:  str   = ""  # "up" | "down" | "neutral" | "unknown"

    @classmethod
    def compute(cls, metric: str, label_he: str, before: Optional[float], after: Optional[float]) -> "ExposureDelta":
        d = None
        direction = "unknown"
        if before is not None and after is not None:
            d = round(after - before, 2)
            direction = "up" if d > 0.1 else ("down" if d < -0.1 else "neutral")
        return cls(metric=metric, label_he=label_he, before=before, after=after, delta_pp=d, direction=direction)


@dataclass
class SelectedScenario:
    """One selected optimization scenario."""
    label:       str   = ""     # e.g. "חלופה משוקללת"
    managers:    str   = ""
    funds:       str   = ""
    tracks:      str   = ""
    weights:     tuple = field(default_factory=tuple)
    stocks_pct:  float = math.nan
    foreign_pct: float = math.nan
    fx_pct:      float = math.nan
    illiquid_pct:float = math.nan
    sharpe:      float = math.nan
    cost:        float = math.nan
    advantage:   str   = ""
    raw_row:     Dict  = field(default_factory=dict)

    @classmethod
    def from_row(cls, label: str, row: dict) -> "SelectedScenario":
        def _f(v):
            try: return float(v) if v is not None else math.nan
            except: return math.nan
        return cls(
            label       = label,
            managers    = str(row.get("מנהלים","")),
            funds       = str(row.get("קופות","")),
            tracks      = str(row.get("מסלולים","")),
            weights     = tuple(row.get("weights",())),
            stocks_pct  = _f(row.get("מניות (%)")),
            foreign_pct = _f(row.get('חו"ל (%)')),
            fx_pct      = _f(row.get('מט"ח (%)')),
            illiquid_pct= _f(row.get("לא־סחיר (%)")),
            sharpe      = _f(row.get("שארפ משוקלל")),
            cost        = _f(row.get("שירות משוקלל")),
            advantage   = str(row.get("יתרון","")),
            raw_row     = dict(row),
        )


@dataclass
class AIReview:
    """Structured AI-generated advisory review."""
    # Section 1: Advisor-facing rationale
    advisor_rationale:   str = ""
    # Section 2: Client-facing explanation
    client_explanation:  str = ""
    # Section 3: Trade-offs and considerations
    trade_offs:          str = ""
    # Section 4: Assumptions and data caveats
    assumptions_text:    str = ""
    # Legacy-compatible fields (from Phase 2)
    executive_summary:   str = ""
    current_weaknesses:  str = ""
    planning_principles: str = ""
    change_advantages:   str = ""
    risks:               str = ""
    final_summary:       str = ""
    generated_at:        str = ""
    tone:                str = "professional"
    mode:                str = "planning"

    def is_complete(self) -> bool:
        return bool(
            (self.advisor_rationale.strip() or self.executive_summary.strip()) and
            (self.final_summary.strip() or self.client_explanation.strip())
        )

    def to_sections_dict(self) -> dict:
        """Export in the existing final_report_sections format."""
        return {
            "executive_summary":    self.executive_summary or self.advisor_rationale,
            "current_weaknesses":   self.current_weaknesses,
            "planning_principles":  self.planning_principles,
            "change_advantages":    self.change_advantages or self.trade_offs,
            "risks_considerations": self.risks or self.assumptions_text,
            "final_summary":        self.final_summary or self.client_explanation,
        }


@dataclass
class ValidationFlags:
    has_holdings:        bool = False
    has_snapshot:        bool = False
    has_optimization:    bool = False
    has_selected_alt:    bool = False
    has_ai_review:       bool = False
    has_before_after:    bool = False
    has_export_package:  bool = False
    missing_alloc_count: int  = 0
    warnings:            List[str] = field(default_factory=list)
    blockers:            List[str] = field(default_factory=list)

    def can_advance_to(self, target_step: int) -> tuple[bool, List[str]]:
        """Return (ok, list_of_reasons) for whether we can move to target_step."""
        reasons = []
        if target_step >= STEP_DATA_INTAKE and not self.has_holdings:
            reasons.append("לא יובאו נתוני תיק עדיין")
        if target_step >= STEP_SNAPSHOT and not self.has_holdings:
            reasons.append("יש להשלים קליטת נתונים לפני תמונת מצב")
        if target_step >= STEP_AI_REVIEW and not self.has_optimization:
            reasons.append("יש לבצע אופטימיזציה ולבחור חלופה לפני הסברי AI")
        if target_step >= STEP_BEFORE_AFTER and not self.has_selected_alt:
            reasons.append("יש לבחור חלופה לפני בניית חבילת לפני/אחרי")
        if target_step >= STEP_EXPORT and not self.has_before_after:
            reasons.append("יש לבנות את חבילת לפני/אחרי לפני הייצוא")
        return (len(reasons) == 0, reasons)


@dataclass
class AdvisoryCase:
    """
    Central source of truth for one client advisory engagement.
    All UI layers read from / write to this via CaseStore.
    Existing engines (optimizer, AI, reports) remain unchanged — 
    CaseStore mirrors to legacy session_state keys.
    """
    # ── Identity ──────────────────────────────────────────────────────────────
    case_id:              str  = ""
    client_name:          str  = "לקוח"
    created_at:           str  = ""
    mode:                 str  = "client"
    flow_intent:          str  = "full"

    # ── Workflow ───────────────────────────────────────────────────────────────
    current_step:         int  = STEP_CASE_SETUP
    step_done:            Dict[int, bool] = field(default_factory=lambda: {s:False for s in range(1,8)})

    # ── Data intake ───────────────────────────────────────────────────────────
    holdings_imported:    List[Dict] = field(default_factory=list)
    holdings_manual:      List[Dict] = field(default_factory=list)
    holdings_normalized:  List[Dict] = field(default_factory=list)
    active_product_type:  str  = "קרנות השתלמות"
    missing_alloc_items:  List[str] = field(default_factory=list)
    mapping_corrections:  List[Dict] = field(default_factory=list)

    # ── Snapshot layer ────────────────────────────────────────────────────────
    current_snapshot:     Optional[PortfolioSnapshot] = None
    current_total:        float = 0.0

    # ── Optimization layer ────────────────────────────────────────────────────
    optimizer_targets:    Dict = field(default_factory=dict)
    selected_scenario:    Optional[SelectedScenario] = None
    planned_changes:      List[Dict] = field(default_factory=list)

    # ── Before / After package ────────────────────────────────────────────────
    proposed_snapshot:    Optional[PortfolioSnapshot] = None
    exposure_deltas:      List[ExposureDelta] = field(default_factory=list)
    change_log:           List[Dict] = field(default_factory=list)
    selected_actions:     List[Dict] = field(default_factory=list)
    scenario_summary:     str  = ""
    assumptions:          List[str] = field(default_factory=list)
    missing_data_notes:   List[str] = field(default_factory=list)

    # ── AI Review ─────────────────────────────────────────────────────────────
    ai_review:            Optional[AIReview] = None

    # ── Export ────────────────────────────────────────────────────────────────
    export_payload:       Optional[Dict] = None
    last_updated:         str  = ""

    # ── Validation ────────────────────────────────────────────────────────────
    validation:           ValidationFlags = field(default_factory=ValidationFlags)

    @property
    def all_holdings(self) -> List[Dict]:
        if self.holdings_normalized:
            return self.holdings_normalized
        return self.holdings_imported + self.holdings_manual

    @property
    def selected_alt(self) -> Optional[str]:
        return self.selected_scenario.label if self.selected_scenario else None

    def mark_step_done(self, step: int) -> None:
        self.step_done[step] = True
        if step == self.current_step and step < STEP_EXPORT:
            self.current_step = step + 1

    def next_incomplete_step(self) -> Optional[int]:
        for s in range(1, 8):
            if not self.step_done.get(s, False): return s
        return None

    def completion_pct(self) -> int:
        done = sum(1 for s in range(1,8) if self.step_done.get(s,False))
        return int(done / 7 * 100)

    def has_before_after(self) -> bool:
        return bool(self.current_snapshot and self.proposed_snapshot)
