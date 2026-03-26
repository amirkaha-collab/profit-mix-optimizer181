# -*- coding: utf-8 -*-
"""
case_management/case_store.py  ·  Phase 3
─────────────────────────────────────────
Streamlit session_state adapter for AdvisoryCase.

Key rules:
- CaseStore.get()  → always returns the latest case, synced from legacy state
- CaseStore.save() → persists case AND mirrors all legacy keys (engines keep working)
- Legacy keys (portfolio_holdings, portfolio_baseline, etc.) remain alive for backward compat
- optimization_results NOT stored in case (too large) — read live from session_state
"""
from __future__ import annotations
import math, uuid
from datetime import datetime
from typing import Optional

import streamlit as st

from case_management import (
    AdvisoryCase, AIReview, ValidationFlags, PortfolioSnapshot, SelectedScenario,
    STEP_CASE_SETUP, STEP_DATA_INTAKE, STEP_SNAPSHOT,
    STEP_OPTIMIZATION, STEP_AI_REVIEW, STEP_BEFORE_AFTER, STEP_EXPORT,
)

_KEY = "advisory_case"


class CaseStore:

    @classmethod
    def get(cls) -> AdvisoryCase:
        if _KEY not in st.session_state:
            cls.save(cls._new())
        case = cls._from_dict(st.session_state.get(_KEY, {}))
        cls._sync_from_legacy(case)
        return case

    @classmethod
    def save(cls, case: AdvisoryCase) -> None:
        cls._sync_to_legacy(case)
        st.session_state[_KEY] = cls._to_dict(case)

    @classmethod
    def reset(cls) -> None:
        if _KEY in st.session_state:
            del st.session_state[_KEY]
        for k in ["last_results","selected_alt","run_history","portfolio_holdings",
                  "portfolio_baseline","portfolio_total","portfolio_managers",
                  "quick_profile_active","final_report_sections","planning_actions",
                  "planning_proposed_portfolio","_client_report_html",
                  "_client_report_comparison","_client_report_actions"]:
            st.session_state[k] = ([] if k == "run_history" else None)

    @classmethod
    def set_mode(cls, mode: str) -> None:
        st.session_state["app_mode"] = mode
        case = cls.get(); case.mode = mode; cls.save(case)

    @classmethod
    def get_mode(cls) -> str:
        return st.session_state.get("app_mode", "home")

    @classmethod
    def mark_step(cls, step: int) -> None:
        case = cls.get(); case.mark_step_done(step); cls.save(case)

    @classmethod
    def set_selected_scenario(cls, label: str, row: dict) -> None:
        """Store a selected optimization scenario into the case."""
        case = cls.get()
        case.selected_scenario = SelectedScenario.from_row(label, row)
        case.step_done[STEP_OPTIMIZATION] = True
        st.session_state["selected_alt"] = label
        cls.save(case)

    @classmethod
    def run_pipeline(cls, df_long=None) -> bool:
        """Run the full before/after pipeline and save."""
        from case_management.before_after_pipeline import run_full_pipeline
        case = cls.get()
        ok = run_full_pipeline(case, df_long)
        cls.save(case)
        return ok

    @classmethod
    def get_workflow_engine(cls):
        """Get a fresh WorkflowEngine for the current case."""
        from case_management.workflow_engine import WorkflowEngine
        return WorkflowEngine.for_case(cls.get())

    # ── Sync helpers ──────────────────────────────────────────────────────────

    @classmethod
    def _sync_from_legacy(cls, case: AdvisoryCase) -> None:
        ss = st.session_state
        # Holdings — client_portfolio writes here
        leg_h = ss.get("portfolio_holdings")
        if leg_h:
            case.holdings_imported = leg_h
            if not case.holdings_normalized:
                case.holdings_normalized = leg_h
            case.step_done[STEP_DATA_INTAKE] = True

        # Baseline — portfolio_analysis writes here
        bl    = ss.get("portfolio_baseline")
        total = float(ss.get("portfolio_total") or 0)
        if bl:
            if not case.current_snapshot or case.current_snapshot.total_value == 0:
                case.current_snapshot = PortfolioSnapshot.from_baseline_dict(bl, total)
            case.current_total = total
            case.step_done[STEP_SNAPSHOT] = True

        # Optimization results
        if ss.get("last_results"):
            case.step_done[STEP_OPTIMIZATION] = True

        # Selected alt — may be set by render_results_table
        alt = ss.get("selected_alt")
        if alt and (not case.selected_scenario or case.selected_scenario.label != alt):
            # Try to find the full row from last_results
            res = ss.get("last_results")
            if res and res.get("solutions_all") is not None:
                try:
                    from streamlit_app import _pick_recommendations
                    sols = res["solutions_all"]
                    if not sols.empty and not case.selected_scenario:
                        # Find the row whose label matches alt, not just iloc[0]
                        recs = _pick_recommendations(sols)
                        # recs is dict of label_key → row_dict
                        # Find the matching row by checking חלופה field
                        matched_row = None
                        label_map = {
                            "חלופה משוקללת": recs.get("weighted"),
                            "הכי מדויקת":    recs.get("accurate"),
                            "שארפ מקסימלי":  recs.get("sharpe"),
                            "שירות מוביל":   recs.get("service"),
                        }
                        matched_row = label_map.get(alt)
                        if matched_row is not None:
                            case.selected_scenario = SelectedScenario.from_row(alt, matched_row)
                        else:
                            # fallback: search by iterating recs
                            for row in [recs.get(k) for k in ("weighted","accurate","sharpe","service")]:
                                if row and str(row.get("חלופה","")) == alt:
                                    case.selected_scenario = SelectedScenario.from_row(alt, row)
                                    break
                except Exception:
                    pass

        # AI sections
        secs = ss.get("final_report_sections")
        if secs:
            if not case.ai_review:
                case.ai_review = AIReview()
            case.ai_review.executive_summary   = secs.get("executive_summary","")
            case.ai_review.current_weaknesses  = secs.get("current_weaknesses","")
            case.ai_review.planning_principles = secs.get("planning_principles","")
            case.ai_review.change_advantages   = secs.get("change_advantages","")
            case.ai_review.risks               = secs.get("risks_considerations","")
            case.ai_review.final_summary       = secs.get("final_summary","")
            if case.ai_review.is_complete():
                case.step_done[STEP_AI_REVIEW] = True

        # Product type
        pt = ss.get("product_type")
        if pt:
            case.active_product_type = pt

        # Optimizer targets
        tgts = ss.get("targets")
        if tgts:
            case.optimizer_targets = dict(tgts)

        # Planning actions
        pa = ss.get("planning_actions")
        if pa:
            case.planned_changes = pa

    @classmethod
    def _sync_to_legacy(cls, case: AdvisoryCase) -> None:
        ss = st.session_state
        h = case.all_holdings
        if h:
            ss["portfolio_holdings"] = h
        if case.current_snapshot and case.current_snapshot.raw:
            ss["portfolio_baseline"] = case.current_snapshot.raw
        if case.current_total:
            ss["portfolio_total"] = case.current_total
        if case.selected_scenario:
            ss["selected_alt"] = case.selected_scenario.label
        if case.active_product_type:
            ss["product_type"] = case.active_product_type
        if case.optimizer_targets:
            ss["targets"] = case.optimizer_targets
        if case.planned_changes:
            ss["planning_actions"] = case.planned_changes
        if case.ai_review:
            ss["final_report_sections"] = case.ai_review.to_sections_dict()
        if case.export_payload:
            ss["notebook_export_payload"] = case.export_payload
        ss["app_mode"] = case.mode

    # ── Serialization ─────────────────────────────────────────────────────────

    @classmethod
    def _new(cls) -> AdvisoryCase:
        return AdvisoryCase(
            case_id    = str(uuid.uuid4())[:8],
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M"),
            mode       = st.session_state.get("app_mode", "home"),
        )

    @classmethod
    def _to_dict(cls, case: AdvisoryCase) -> dict:
        def clean(v):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)): return None
            if isinstance(v, dict): return {k: clean(x) for k, x in v.items()}
            if isinstance(v, list): return [clean(x) for x in v]
            return v
        sc = case.selected_scenario
        return {
            "case_id": case.case_id, "client_name": case.client_name,
            "created_at": case.created_at, "mode": case.mode,
            "flow_intent": case.flow_intent, "current_step": case.current_step,
            "step_done": {str(k):v for k,v in case.step_done.items()},
            "active_product_type": case.active_product_type,
            "holdings_imported": clean(case.holdings_imported)[:100],
            "holdings_manual":   clean(case.holdings_manual),
            "current_total":     case.current_total,
            "current_snapshot":  case.current_snapshot.to_dict() if case.current_snapshot else None,
            "proposed_snapshot": case.proposed_snapshot.to_dict() if case.proposed_snapshot else None,
            "selected_scenario": {
                "label": sc.label, "managers": sc.managers, "funds": sc.funds,
                "tracks": sc.tracks, "stocks_pct": clean(sc.stocks_pct),
                "foreign_pct": clean(sc.foreign_pct), "fx_pct": clean(sc.fx_pct),
                "illiquid_pct": clean(sc.illiquid_pct), "sharpe": clean(sc.sharpe),
                "cost": clean(sc.cost), "advantage": sc.advantage,
            } if sc else None,
            "optimizer_targets": clean(case.optimizer_targets),
            "planned_changes":   clean(case.planned_changes),
            "exposure_deltas":   [
                {"metric":d.metric,"label_he":d.label_he,"before":clean(d.before),
                 "after":clean(d.after),"delta_pp":clean(d.delta_pp),"direction":d.direction}
                for d in case.exposure_deltas
            ],
            "scenario_summary": case.scenario_summary,
            "assumptions": case.assumptions, "missing_data_notes": case.missing_data_notes,
            "ai_review": {
                "advisor_rationale":   case.ai_review.advisor_rationale,
                "client_explanation":  case.ai_review.client_explanation,
                "trade_offs":          case.ai_review.trade_offs,
                "assumptions_text":    case.ai_review.assumptions_text,
                "executive_summary":   case.ai_review.executive_summary,
                "current_weaknesses":  case.ai_review.current_weaknesses,
                "planning_principles": case.ai_review.planning_principles,
                "change_advantages":   case.ai_review.change_advantages,
                "risks":               case.ai_review.risks,
                "final_summary":       case.ai_review.final_summary,
                "tone":                case.ai_review.tone,
            } if case.ai_review else None,
            "export_payload_ready": (case.export_payload is not None),
            # export_payload itself is stored in session_state to avoid size issues,
            # but we record whether it was built so the flag survives rerun
        }

    @classmethod
    def _from_dict(cls, d: dict) -> AdvisoryCase:
        if not isinstance(d, dict): return cls._new()
        def _f(v):
            try: x=float(v); return x if not (math.isnan(x) or math.isinf(x)) else math.nan
            except: return math.nan

        sc_d = d.get("selected_scenario")
        sc = None
        if sc_d:
            sc = SelectedScenario(
                label=sc_d.get("label",""), managers=sc_d.get("managers",""),
                funds=sc_d.get("funds",""), tracks=sc_d.get("tracks",""),
                stocks_pct=_f(sc_d.get("stocks_pct")), foreign_pct=_f(sc_d.get("foreign_pct")),
                fx_pct=_f(sc_d.get("fx_pct")), illiquid_pct=_f(sc_d.get("illiquid_pct")),
                sharpe=_f(sc_d.get("sharpe")), cost=_f(sc_d.get("cost")),
                advantage=sc_d.get("advantage",""),
            )

        def _snap(sd):
            if not sd: return None
            s = PortfolioSnapshot()
            s.total_value  = float(sd.get("total_value") or 0)
            s.stocks_pct   = _f(sd.get("stocks_pct"))
            s.foreign_pct  = _f(sd.get("foreign_pct"))
            s.fx_pct       = _f(sd.get("fx_pct"))
            s.illiquid_pct = _f(sd.get("illiquid_pct"))
            s.sharpe       = _f(sd.get("sharpe"))
            s.cost_pct     = _f(sd.get("cost_pct"))
            s.raw          = sd.get("raw") or {}
            return s

        from case_management import ExposureDelta
        deltas = [
            ExposureDelta(metric=x.get("metric",""),label_he=x.get("label_he",""),
                         before=x.get("before"),after=x.get("after"),
                         delta_pp=x.get("delta_pp"),direction=x.get("direction",""))
            for x in (d.get("exposure_deltas") or [])
        ]

        case = AdvisoryCase(
            case_id=d.get("case_id",""), client_name=d.get("client_name","לקוח"),
            created_at=d.get("created_at",""), mode=d.get("mode","home"),
            flow_intent=d.get("flow_intent","full"),
            current_step=int(d.get("current_step",STEP_CASE_SETUP)),
            step_done={int(k):v for k,v in d.get("step_done",{}).items()} or {s:False for s in range(1,8)},
            active_product_type=d.get("active_product_type","קרנות השתלמות"),
            holdings_imported=d.get("holdings_imported") or [],
            holdings_manual=d.get("holdings_manual") or [],
            current_total=float(d.get("current_total") or 0),
            current_snapshot=_snap(d.get("current_snapshot")),
            proposed_snapshot=_snap(d.get("proposed_snapshot")),
            selected_scenario=sc,
            optimizer_targets=d.get("optimizer_targets") or {},
            planned_changes=d.get("planned_changes") or [],
            exposure_deltas=deltas,
            scenario_summary=d.get("scenario_summary",""),
            assumptions=d.get("assumptions") or [],
            missing_data_notes=d.get("missing_data_notes") or [],
        )
        ai = d.get("ai_review")
        if ai:
            case.ai_review = AIReview(**{k:v for k,v in ai.items() if k in AIReview.__dataclass_fields__})
        # Restore export_payload from session_state if it was saved there
        try:
            import streamlit as _st2
            ep = _st2.session_state.get("notebook_export_payload")
            if ep:
                case.export_payload = ep
                case.step_done[7] = True
        except Exception:
            pass
        return case
