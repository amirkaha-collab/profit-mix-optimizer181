# -*- coding: utf-8 -*-
"""
case_management/workflow_engine.py  ·  Phase 3
────────────────────────────────────────────────
Real workflow orchestrator for Client Mode.

Responsibilities:
- Define 7 formal steps with validation rules
- Enforce allowed transitions (no skipping without data)
- Compute completeness / readiness at each step
- Provide step status for UI (done / active / blocked / upcoming)
- NOT responsible for rendering — purely data/logic

Public API:
    engine = WorkflowEngine.for_case(case)
    engine.can_advance(target_step)   → (bool, [reasons])
    engine.get_status()               → {step: StepStatus}
    engine.validate_current()         → ValidationFlags
    engine.advance_if_valid(step)     → (bool, [reasons])
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from case_management import (
    AdvisoryCase, ValidationFlags,
    STEP_CASE_SETUP, STEP_DATA_INTAKE, STEP_SNAPSHOT,
    STEP_OPTIMIZATION, STEP_AI_REVIEW, STEP_BEFORE_AFTER, STEP_EXPORT,
    STEP_LABELS, STEP_ICONS,
)


@dataclass
class StepStatus:
    step:      int
    label:     str
    icon:      str
    done:      bool
    active:    bool
    blocked:   bool    # cannot enter yet
    blockers:  List[str]  # why it's blocked


class WorkflowEngine:
    """
    Stateless workflow engine for AdvisoryCase.
    Created fresh each render from the case — no internal state.
    """

    def __init__(self, case: AdvisoryCase):
        self._case = case
        self._flags = self._compute_flags()

    @classmethod
    def for_case(cls, case: AdvisoryCase) -> "WorkflowEngine":
        return cls(case)

    # ── Transition rules ──────────────────────────────────────────────────────

    # Maps step → minimum data conditions as lambda(case, flags) → list of blocking reasons
    _TRANSITION_RULES: Dict[int, callable] = {
        STEP_CASE_SETUP:   lambda c, f: [],
        STEP_DATA_INTAKE:  lambda c, f: [],  # always reachable
        STEP_SNAPSHOT:     lambda c, f: (
            ["יש להשלים קליטת נתונים ראשונה"] if not f.has_holdings else []
        ),
        STEP_OPTIMIZATION: lambda c, f: (
            ["יש להשלים קליטת נתונים ראשונה"] if not f.has_holdings else []
        ),
        STEP_AI_REVIEW:    lambda c, f: (
            (["יש לבצע אופטימיזציה ולבחור חלופה לפני הסברי AI"] if not f.has_selected_alt else [])
        ),
        STEP_BEFORE_AFTER: lambda c, f: (
            (["יש לבחור חלופה מהאופטימיזציה לפני בניית חבילת לפני/אחרי"] if not f.has_selected_alt else [])
        ),
        STEP_EXPORT:       lambda c, f: (
            (["יש לבנות את חבילת לפני/אחרי לפני הייצוא"] if not f.has_before_after else [])
        ),
    }

    def can_advance(self, target_step: int) -> Tuple[bool, List[str]]:
        """Return (ok, blocking_reasons)."""
        rule = self._TRANSITION_RULES.get(target_step)
        if rule is None:
            return (False, [f"שלב לא מוכר: {target_step}"])
        reasons = rule(self._case, self._flags)
        return (len(reasons) == 0, reasons)

    def advance_if_valid(self, target_step: int) -> Tuple[bool, List[str]]:
        """Mark step done and advance current_step if rules pass."""
        ok, reasons = self.can_advance(target_step)
        if ok:
            prev = target_step - 1
            if prev >= STEP_CASE_SETUP:
                self._case.mark_step_done(prev)
            self._case.current_step = target_step
        return ok, reasons

    # ── Status for UI ─────────────────────────────────────────────────────────

    def get_status(self) -> Dict[int, StepStatus]:
        """Return display status for all 7 steps."""
        statuses = {}
        active_step = self._case.current_step
        for s in range(1, 8):
            done     = self._case.step_done.get(s, False)
            active   = (s == active_step)
            ok, blk  = self.can_advance(s)
            blocked  = (not done and not active and not ok)
            statuses[s] = StepStatus(
                step     = s,
                label    = STEP_LABELS.get(s, ""),
                icon     = STEP_ICONS.get(s, ""),
                done     = done,
                active   = active,
                blocked  = blocked,
                blockers = blk if blocked else [],
            )
        return statuses

    def current_status(self) -> StepStatus:
        return self.get_status()[self._case.current_step]

    # ── Completeness ──────────────────────────────────────────────────────────

    def _compute_flags(self) -> ValidationFlags:
        c = self._case
        f = ValidationFlags()
        h = c.all_holdings
        f.has_holdings       = bool(h)
        f.has_snapshot       = bool(c.current_snapshot)
        f.has_optimization   = bool(c.step_done.get(STEP_OPTIMIZATION))
        f.has_selected_alt   = bool(c.selected_scenario)
        f.has_ai_review      = bool(c.ai_review and c.ai_review.is_complete())
        f.has_before_after   = c.has_before_after()
        f.has_export_package = bool(c.export_payload)
        f.missing_alloc_count = sum(
            1 for x in h
            if x.get("equity_pct") is None or
               str(x.get("equity_pct","")).strip() in ("","nan","None")
        )
        if not f.has_holdings:
            f.warnings.append("טרם יובאו נתוני תיק — נדרש לשלב קליטת נתונים")
        if f.missing_alloc_count:
            f.warnings.append(f"{f.missing_alloc_count} מוצרים ללא נתוני חשיפה — ניתן להשלים ידנית")
        if f.has_holdings and not f.has_snapshot:
            f.warnings.append("תמונת מצב טרם חושבה — לחץ 'חשב baseline'")
        if f.has_snapshot and not f.has_selected_alt:
            f.warnings.append("אופטימיזציה טרם בוצעה")
        if f.has_selected_alt and not f.has_before_after:
            f.warnings.append("חבילת לפני/אחרי טרם נבנתה")
        return f

    def get_flags(self) -> ValidationFlags:
        return self._flags
