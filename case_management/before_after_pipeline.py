# -*- coding: utf-8 -*-
"""
case_management/before_after_pipeline.py  ·  Phase 3
──────────────────────────────────────────────────────
Formal pipeline for computing and storing the Before/After package.

All numeric truth comes from existing engines.
This module assembles, stores, and validates the comparison package.

Public API:
    compute_baseline(case, df_long)   → updates case.current_snapshot
    compute_proposed(case, rec_row)   → updates case.proposed_snapshot
    compute_deltas(case)              → updates case.exposure_deltas
    build_export_bundle(case)         → builds case.export_payload
"""
from __future__ import annotations
import json, math
from datetime import datetime
from typing import Dict, List, Optional, Any

from case_management import (
    AdvisoryCase, PortfolioSnapshot, ExposureDelta, SelectedScenario,
    STEP_BEFORE_AFTER, STEP_EXPORT,
)


def _f(v) -> Optional[float]:
    """Safe float cast; None for NaN/None."""
    try:
        x = float(v)
        return None if math.isnan(x) or math.isinf(x) else x
    except (TypeError, ValueError):
        return None


def _clean(obj):
    """Recursively replace NaN/Inf with None for JSON serialization."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else round(obj, 4)
    if isinstance(obj, dict):  return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)): return [_clean(v) for v in obj]
    return obj


# ── Step 1: Baseline ──────────────────────────────────────────────────────────

def compute_baseline(case: AdvisoryCase, df_long=None) -> bool:
    """
    Build case.current_snapshot from session_state["portfolio_baseline"].
    Falls back to computing from holdings if baseline not set.
    Returns True if snapshot was successfully built.
    """
    try:
        import streamlit as st
        bl    = st.session_state.get("portfolio_baseline") or {}
        total = float(st.session_state.get("portfolio_total") or 0)

        if not bl and case.all_holdings and df_long is not None:
            # Compute baseline using the existing engine function
            # We import it from streamlit_app via a lazy import to avoid circular refs
            try:
                import sys, os
                sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
                from streamlit_app import _compute_baseline_from_holdings
                bl = _compute_baseline_from_holdings(case.all_holdings, df_long) or {}
                if bl:
                    total = bl.get("amount", total)
                    st.session_state["portfolio_baseline"] = bl
            except Exception:
                pass

        if bl:
            case.current_snapshot = PortfolioSnapshot.from_baseline_dict(bl, total)
            case.current_total    = total
            case.step_done[3]     = True
            return True
        return False
    except Exception:
        return False


# ── Step 2: Proposed snapshot ────────────────────────────────────────────────

def compute_proposed(case: AdvisoryCase) -> bool:
    """
    Build case.proposed_snapshot from case.selected_scenario.
    Returns True if proposed snapshot was successfully built.
    """
    sc = case.selected_scenario
    if not sc:
        return False

    case.proposed_snapshot = PortfolioSnapshot(
        total_value  = case.current_total or 0.0,
        stocks_pct   = _f(sc.stocks_pct)   or math.nan,
        foreign_pct  = _f(sc.foreign_pct)  or math.nan,
        fx_pct       = _f(sc.fx_pct)       or math.nan,
        illiquid_pct = _f(sc.illiquid_pct) or math.nan,
        sharpe       = _f(sc.sharpe)       or math.nan,
        cost_pct     = _f(sc.cost)         or math.nan,
        raw          = sc.raw_row,
    )
    return True


# ── Step 3: Deltas ────────────────────────────────────────────────────────────

_DELTA_METRICS = [
    ("stocks",    "מניות %"),
    ("foreign",   'חו"ל %'),
    ("fx",        'מט"ח %'),
    ("illiquid",  "לא-סחיר %"),
    ("sharpe",    "שארפ"),
    ("cost",      "עלות %"),
]

def compute_deltas(case: AdvisoryCase) -> bool:
    """
    Compute exposure deltas between current and proposed snapshots.
    Stores structured ExposureDelta objects in case.exposure_deltas.
    """
    cur = case.current_snapshot
    prp = case.proposed_snapshot
    if not cur or not prp:
        return False

    def _get(snap: PortfolioSnapshot, metric: str) -> Optional[float]:
        if metric == "stocks":    return _f(snap.stocks_pct)
        if metric == "foreign":   return _f(snap.foreign_pct)
        if metric == "fx":        return _f(snap.fx_pct)
        if metric == "illiquid":  return _f(snap.illiquid_pct)
        if metric == "sharpe":    return _f(snap.sharpe)
        if metric == "cost":      return _f(snap.cost_pct)
        return None

    case.exposure_deltas = [
        ExposureDelta.compute(metric, label, _get(cur, metric), _get(prp, metric))
        for metric, label in _DELTA_METRICS
    ]
    case.step_done[STEP_BEFORE_AFTER] = True
    return True


def run_full_pipeline(case: AdvisoryCase, df_long=None) -> bool:
    """
    Run the complete before/after pipeline in one call.
    Safe to call multiple times — idempotent.
    """
    ok1 = compute_baseline(case, df_long)
    ok2 = compute_proposed(case)
    ok3 = compute_deltas(case)
    return ok1 and ok2 and ok3


# ── Export bundle ─────────────────────────────────────────────────────────────

def build_export_bundle(case: AdvisoryCase) -> dict:
    """
    Build a complete, production-ready Notebook export payload from the case.
    All NaN replaced with None. No JSON-in-strings. Typed slides.
    """
    from datetime import datetime as dt

    ai    = case.ai_review
    cur   = case.current_snapshot
    prp   = case.proposed_snapshot
    sc    = case.selected_scenario
    delts = case.exposure_deltas

    def _snap_dict(snap: Optional[PortfolioSnapshot]) -> dict:
        if not snap: return {}
        return _clean({
            "total_value":   snap.total_value,
            "stocks_pct":    snap.stocks_pct,
            "foreign_pct":   snap.foreign_pct,
            "fx_pct":        snap.fx_pct,
            "illiquid_pct":  snap.illiquid_pct,
            "sharpe":        snap.sharpe,
            "cost_pct":      snap.cost_pct,
            "n_products":    snap.n_products,
            "n_managers":    snap.n_managers,
        })

    delta_rows = [
        {
            "metric":            d.metric,
            "label":             d.label_he,
            "before":            _clean(d.before),
            "after":             _clean(d.after),
            "delta_pp":          _clean(d.delta_pp),
            "direction":         d.direction,
            "availability_note": None if d.before is not None else "אין נתוני מצב קיים",
        }
        for d in delts
    ] if delts else []

    # Data completeness
    has_cur   = bool(cur)
    has_prp   = bool(prp)
    complete  = "full" if has_cur and has_prp else ("partial" if has_prp else "none")

    slides = [
        {"slide":1,"type":"cover",
         "title":"שער",
         "content":f"דוח לקוח — {case.client_name}",
         "subtitle":"הופק על-ידי Profit Financial Group · Alpha Optimizer",
         "report_type":"דוח מלא" if complete=="full" else "דוח חלקי"},
        {"slide":2,"type":"text",
         "title":"תקציר מנהלים",
         "content": ai.executive_summary if ai else ""},
        {"slide":3,"type":"data",
         "title":"תיק נוכחי",
         "content":"מצב קיים" if has_cur else "נתונים חלקיים",
         "data": _snap_dict(cur),
         "availability": "available" if has_cur else "unavailable"},
        {"slide":4,"type":"data",
         "title":"תיק מוצע",
         "content":f"חלופה נבחרת: {sc.label if sc else 'לא נבחר'}",
         "data": _snap_dict(prp),
         "availability": "available" if has_prp else "unavailable"},
        {"slide":5,"type":"table",
         "title":"השוואה לפני / אחרי",
         "content":"שינויים בחשיפות",
         "data": delta_rows,
         "columns":["label","before","after","delta_pp","direction","availability_note"],
         "has_full_comparison": has_cur and has_prp},
        {"slide":6,"type":"text",
         "title":"יתרונות השינויים",
         "content": (ai.change_advantages or ai.trade_offs) if ai else ""},
        {"slide":7,"type":"text",
         "title":"שיקולים ואיזונים",
         "content": (ai.risks or ai.assumptions_text) if ai else ""},
        {"slide":8,"type":"text",
         "title":"סיכום סופי",
         "content": (ai.final_summary or ai.client_explanation) if ai else ""},
    ]

    bundle = {
        "notebook_schema_version": "3.1",
        "generated_at":            dt.now().strftime("%Y-%m-%d %H:%M"),
        "mode":                    "planning",
        "report_mode":             case.flow_intent,
        "data_completeness":       complete,
        "export_ready":            has_prp,
        "case_id":                 case.case_id,
        "client_name":             case.client_name,
        "active_product_type":     case.active_product_type,
        "selected_scenario": {
            "label":        sc.label       if sc else None,
            "managers":     sc.managers    if sc else None,
            "funds":        sc.funds       if sc else None,
            "advantage":    sc.advantage   if sc else None,
        },
        "portfolio_before":  _snap_dict(cur),
        "portfolio_after":   _snap_dict(prp),
        "exposure_deltas":   delta_rows,
        "planned_changes":   _clean(case.planned_changes),
        "scenario_summary":  case.scenario_summary,
        "ai_sections": ai.to_sections_dict() if ai else {
            k:"" for k in ["executive_summary","current_weaknesses",
                            "planning_principles","change_advantages",
                            "risks_considerations","final_summary"]
        },
        "assumptions":        case.assumptions,
        "missing_data_notes": case.missing_data_notes,
        "presentation_slides": slides,
        "notebook_instructions": {
            "do_not_invent_values": True,
            "language":             "Hebrew RTL",
            "style":                "professional family-office",
            "missing_data_policy":  "Show unavailable fields explicitly; do not estimate",
            "chart_policy":         "Build charts only from valid non-null numeric values",
            "slides_count":         8,
        },
    }
    return bundle
