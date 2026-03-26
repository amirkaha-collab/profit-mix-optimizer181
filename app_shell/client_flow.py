# -*- coding: utf-8 -*-
"""
app_shell/client_flow.py  ·  Phase 3
──────────────────────────────────────
Client Mode wizard.

Architecture:
- WorkflowEngine validates transitions
- CaseStore is the single data source
- Each step renders its UI then writes back to the case
- Steps 1-4,6-7 are self-contained (call st.stop())
- Step 5 (optimization) falls through to the main render block

The wizard renders:
1. Mode header + case status bar
2. Step navigation (with validation-aware blocking)
3. Step content (delegates to existing engines)
4. Next-step CTA (only when step is completable)
"""
from __future__ import annotations
import streamlit as st
from case_management import (
    STEP_CASE_SETUP, STEP_DATA_INTAKE, STEP_SNAPSHOT,
    STEP_OPTIMIZATION, STEP_AI_REVIEW, STEP_BEFORE_AFTER, STEP_EXPORT,
    STEP_LABELS, STEP_ICONS,
)
from case_management.case_store import CaseStore
from case_management.workflow_engine import WorkflowEngine, StepStatus

_WIZ_CSS = """
<style>
.wiz-bar{background:#fff;border:1px solid #e2e8f0;border-radius:12px;
  padding:12px 20px 10px;margin-bottom:16px;direction:rtl}
.wiz-bar-mode{font-size:8.5px;font-weight:800;letter-spacing:2.5px;
  text-transform:uppercase;color:#2563eb;margin-bottom:8px}
.wiz-nodes{display:flex;align-items:flex-start;gap:0}
.wiz-node{flex:1;display:flex;flex-direction:column;align-items:center;position:relative}
.wiz-node:not(:last-child)::after{content:'';position:absolute;top:12px;
  right:calc(-50% + 12px);width:calc(100% - 24px);height:2px;
  background:var(--lc,#e2e8f0);z-index:0}
.wiz-node.done::after{--lc:#2563eb}
.wiz-dot{width:32px;height:32px;border-radius:50%;z-index:1;
  display:flex;align-items:center;justify-content:center;
  font-size:10px;font-weight:800;position:relative;
  background:var(--nb,#f1f5f9);border:2px solid var(--nbd,#e2e8f0);color:var(--nc,#94a3b8)}
.wiz-node.done   .wiz-dot{--nb:#eff6ff;--nbd:#2563eb;--nc:#2563eb}
.wiz-node.active .wiz-dot{--nb:#0f2d5e;--nbd:#0f2d5e;--nc:#fff;
  box-shadow:0 0 0 4px rgba(15,45,94,.12)}
.wiz-node.blocked .wiz-dot{--nb:#fef3c7;--nbd:#fde68a;--nc:#b45309;opacity:.7}
.wiz-lbl{font-size:11.5px;font-weight:700;margin-top:7px;
  color:var(--lbl,#94a3b8);text-align:center;line-height:1.35;max-width:80px}
.wiz-node.done   .wiz-lbl{--lbl:#1d4ed8;font-weight:800}
.wiz-node.active .wiz-lbl{--lbl:#0b1929;font-weight:900}
.wiz-node.blocked .wiz-lbl{--lbl:#b45309;font-size:10.5px}
.wiz-step-header{background:linear-gradient(135deg,#0b1f42,#0f2d5e);
  border-radius:12px;padding:12px 18px;direction:rtl;text-align:right;
  margin-bottom:14px;display:flex;align-items:center;justify-content:space-between}
.wiz-sh-left{display:flex;flex-direction:column;gap:3px}
.wiz-sh-lbl{font-size:8.5px;font-weight:800;letter-spacing:2px;
  text-transform:uppercase;color:rgba(96,165,250,.7)}
.wiz-sh-title{font-size:17px;font-weight:900;color:#fff}
.wiz-sh-desc{font-size:11.5px;color:rgba(186,214,254,.65)}
.wiz-sh-pct{font-size:26px;font-weight:900;color:rgba(255,255,255,.2)}
.wiz-next{background:linear-gradient(135deg,#f0fdf4,#dcfce7);
  border:1.5px solid #86efac;border-radius:12px;
  padding:14px 18px;direction:rtl;text-align:right;margin-top:16px}
.wiz-next-title{font-size:13px;font-weight:800;color:#065f46;margin-bottom:3px}
.wiz-next-desc{font-size:12px;color:#047857}
.wiz-blocker{background:#fef3c7;border:1px solid #fde68a;border-right:3px solid #f59e0b;
  border-radius:8px;padding:8px 14px;direction:rtl;text-align:right;margin-top:10px}
</style>
"""

_STEP_DESCS = {
    STEP_CASE_SETUP:   "בחר לקוח, הגדר סוג תהליך",
    STEP_DATA_INTAKE:  "העלה מסלקה, הוסף מוצרים ידנית, השלם נתוני חשיפה",
    STEP_SNAPSHOT:     "תמונת מצב משוקללת של כלל התיק הנוכחי",
    STEP_OPTIMIZATION: "הגדר יעדים, הפעל אופטימיזציה, בחר חלופה",
    STEP_AI_REVIEW:    "הסבר AI מבוסס-נתונים — ניתן לערוך ולאשר",
    STEP_BEFORE_AFTER: "חבילת השוואה לפני / אחרי — מוכנה לאישור",
    STEP_EXPORT:       "ייצוא חבילה מלאה לנוטבוק ולהצגה ללקוח",
}


def render_client_wizard(df_long, nav_to_fn) -> None:
    """
    Main wizard entry point.
    Called from streamlit_app.py routing block.
    Self-contained steps call st.stop().
    Step 5 (OPTIMIZATION) returns without stopping — falls through.
    """
    st.markdown(_WIZ_CSS, unsafe_allow_html=True)

    case   = CaseStore.get()
    engine = WorkflowEngine.for_case(case)
    step   = st.session_state.get("client_wizard_step", case.current_step or STEP_DATA_INTAKE)
    flags  = engine.get_flags()
    status = engine.get_status()
    pct    = case.completion_pct()

    # ── Step progress bar ──────────────────────────────────────────────────────
    _render_progress_bar(status, step)

    # ── Step header ────────────────────────────────────────────────────────────
    lbl  = STEP_LABELS.get(step, "")
    icon = STEP_ICONS.get(step, "")
    desc = _STEP_DESCS.get(step, "")
    st.markdown(f"""
<div class="wiz-step-header">
  <div class="wiz-sh-left">
    <div class="wiz-sh-lbl">שלב {step} מתוך 7 · עבודה עם לקוח</div>
    <div class="wiz-sh-title">{icon} {lbl}</div>
    <div class="wiz-sh-desc">{desc}</div>
  </div>
  <div class="wiz-sh-pct">{pct}%</div>
</div>""", unsafe_allow_html=True)

    # ── Validation warnings ─────────────────────────────────────────────────────
    if flags.warnings and step > STEP_DATA_INTAKE:
        for w in flags.warnings[:2]:  # show max 2
            st.caption(f"⚠️ {w}")

    # ── Route to step content ──────────────────────────────────────────────────
    SELF_CONTAINED = (STEP_CASE_SETUP, STEP_DATA_INTAKE, STEP_SNAPSHOT,
                      STEP_AI_REVIEW, STEP_BEFORE_AFTER, STEP_EXPORT)

    if step == STEP_CASE_SETUP:
        _step_case_setup(case, engine)
        st.stop()

    elif step == STEP_DATA_INTAKE:
        _step_data_intake(case, df_long, engine)
        st.stop()

    elif step == STEP_SNAPSHOT:
        _step_snapshot(case, df_long, engine)
        st.stop()

    elif step == STEP_OPTIMIZATION:
        _step_optimize_header(case, engine)
        # DO NOT stop — fall through to main render block

    elif step == STEP_AI_REVIEW:
        _step_ai_review(case, engine)
        st.stop()

    elif step == STEP_BEFORE_AFTER:
        _step_before_after(case, df_long, engine)
        st.stop()

    elif step == STEP_EXPORT:
        _step_export(case, engine)
        st.stop()


# ── Step renderers ────────────────────────────────────────────────────────────

def _step_case_setup(case, engine: WorkflowEngine) -> None:
    """Step 1: Case setup — client name + flow intent."""
    st.markdown("#### 📁 פתיחת תיק עבודה")

    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("שם הלקוח", value=case.client_name or "לקוח", key="setup_name")
    with col2:
        intent = st.radio("סוג תהליך", ["full", "analysis_only"],
                          format_func=lambda x: "תהליך אופטימיזציה מלא" if x=="full" else "ניתוח מצב קיים בלבד",
                          index=0 if case.flow_intent=="full" else 1, key="setup_intent",
                          horizontal=True)

    # Existing case indicator
    has_data = bool(case.all_holdings)
    if has_data:
        st.info(f"✅ תיק קיים: {len(case.all_holdings)} מוצרים · לחץ 'המשך' לשלב קליטת נתונים", icon="💼")

    col_save, col_reset, _ = st.columns([1, 1, 4])
    with col_save:
        if st.button("💾 שמור והמשך", key="setup_save", type="primary", use_container_width=True):
            case.client_name  = name
            case.flow_intent  = intent
            case.mark_step_done(STEP_CASE_SETUP)
            CaseStore.save(case)
            st.session_state["client_wizard_step"] = STEP_DATA_INTAKE
            st.rerun()
    with col_reset:
        if st.button("🔄 תיק חדש", key="setup_reset", use_container_width=True):
            CaseStore.reset()
            st.session_state["client_wizard_step"] = STEP_CASE_SETUP
            st.rerun()


def _step_data_intake(case, df_long, engine: WorkflowEngine) -> None:
    """
    Step 2 — קליטת נתונים.
    Redesigned: compact, RTL, Hebrew, no auto-advance.
    Upload stays on this step; only explicit button advances to step 3.
    """
    # ── Section header ─────────────────────────────────────────────────────
    st.markdown("""
<div dir="rtl" style="text-align:right;padding:4px 0 12px">
  <div style="font-size:11px;font-weight:800;letter-spacing:2px;color:#2563eb;
       text-transform:uppercase;margin-bottom:4px">שלב קליטת נתונים</div>
  <div style="font-size:18px;font-weight:900;color:#0b1929;margin-bottom:3px">
    העלאת נתוני תיק
  </div>
  <div style="font-size:12.5px;color:#475569">
    ייבא דוח מסלקה פנסיונית או הוסף מוצרים ידנית — ניתן לשלב בין שניהם
  </div>
</div>""", unsafe_allow_html=True)

    # ── Holdings summary — always read fresh from CaseStore ─────────────────
    # Re-read here so summary reflects all previous reruns' changes
    case = CaseStore.get()
    holdings = case.all_holdings
    n = len(holdings)
    if n > 0:
        n_miss = sum(1 for h in holdings
                     if not h.get("equity_pct") and h.get("equity_pct") != 0.0)
        total_ils = sum(h.get("amount", 0) for h in holdings)
        pct_ok = int((n - n_miss) / max(n, 1) * 100)
        clr = "#065f46" if pct_ok == 100 else ("#92400e" if pct_ok < 70 else "#1e40af")
        bg  = "#d1fae5" if pct_ok == 100 else ("#fef3c7" if pct_ok < 70 else "#eff6ff")
        st.markdown(
            f'<div dir="rtl" style="background:{bg};border:1px solid;border-radius:10px;'
            f'padding:10px 16px;margin-bottom:14px;display:flex;gap:20px;'
            f'align-items:center;border-color:{clr}40">'
            f'<div><strong style="color:{clr};font-size:13px">{n}</strong>'
            f'<div style="font-size:10px;color:{clr}">מוצרים</div></div>'
            f'<div><strong style="color:{clr};font-size:13px">'
            f'{"₪{:,.0f}".format(total_ils)}</strong>'
            f'<div style="font-size:10px;color:{clr}">סה"כ</div></div>'
            f'<div><strong style="color:{clr};font-size:13px">{pct_ok}%</strong>'
            f'<div style="font-size:10px;color:{clr}">שלמות חשיפות</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        # Simple holdings table
        import pandas as _pd
        _rows = []
        for h in holdings[:25]:  # cap display at 25
            _rows.append({
                "סוג": h.get("product_type",""),
                "מנהל": h.get("provider",""),
                "מוצר": h.get("product_name",""),
                "מסלול": h.get("track","")[:20] if h.get("track") else "",
                "סכום": "₪{:,.0f}".format(h.get("amount",0)),
                "מניות": "{:.0f}%".format(h["equity_pct"]) if h.get("equity_pct") else "—",
            })
        if _rows:
            st.dataframe(_pd.DataFrame(_rows), use_container_width=True, hide_index=True)
        if n > 25:
            st.caption(f"מוצגים 25 מתוך {n} מוצרים")

    # ══════ Section A: ייבוא מסלקה ═══════════════════════════════════════════
    st.markdown("""
<div dir="rtl" style="background:#f8fafc;border:1px solid #e2e8f0;border-right:3px solid #2563eb;
     border-radius:8px;padding:10px 16px 6px;margin:14px 0 8px">
  <div style="font-size:12px;font-weight:800;color:#1e40af;margin-bottom:2px">
    📤 א. ייבוא דוח מסלקה פנסיונית
  </div>
  <div style="font-size:11px;color:#475569">
    קובץ Excel מגמל-נט או ממשרד האוצר (XLSX)
  </div>
</div>""", unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "העלה קובץ מסלקה",
        type=["xlsx", "xls"],
        key="wizard_clearing_upload",
        label_visibility="collapsed",
    )
    if uploaded is not None:
        with st.spinner("מנתח דוח מסלקה..."):
            try:
                import sys as _sys, os as _os
                _sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
                from streamlit_app import parse_clearing_report, _compute_baseline_from_holdings
                result, err_msg = parse_clearing_report(uploaded.read())
                if err_msg and not result:
                    st.error(f"שגיאת פרסינג: {err_msg}")
                else:
                    if err_msg:
                        st.warning(err_msg)
                    holdings_raw = (result or {}).get("holdings", [])
                    if holdings_raw:
                        # Save to case — NO step change, NO page change
                        st.session_state["portfolio_holdings"] = holdings_raw
                        st.session_state["portfolio_total"]    = sum(h.get("amount", 0) for h in holdings_raw)
                        st.session_state["portfolio_managers"] = list({h.get("provider", "") for h in holdings_raw})
                        _upd = CaseStore.get()
                        _upd.holdings_imported   = holdings_raw
                        _upd.holdings_normalized = holdings_raw
                        _upd.current_total       = st.session_state["portfolio_total"]
                        _upd.step_done[STEP_DATA_INTAKE] = True
                        bl = _compute_baseline_from_holdings(holdings_raw, df_long)
                        if bl:
                            from case_management import PortfolioSnapshot
                            _upd.current_snapshot = PortfolioSnapshot.from_baseline_dict(
                                bl, _upd.current_total)
                            st.session_state["portfolio_baseline"] = bl
                            # NOTE: STEP_SNAPSHOT is NOT marked done here.
                            # Snapshot data is PREPARED but the step is considered done
                            # only when the user actually navigates to step 3 and views it.
                        CaseStore.save(_upd)
                        # Stay on this step — show success then re-render intake
                        st.success(
                            f"✅ יובאו {len(holdings_raw)} מוצרים מהמסלקה. "
                            "ניתן להוסיף מוצרים ידנית או לעבור לשלב הבא."
                        )
                        # st.rerun() causes the page to re-render step 2 with new data
                        st.rerun()
                    else:
                        st.warning("לא נמצאו אחזקות בקובץ — בדוק שהקובץ תקין.")
            except Exception as _e:
                st.error(f"שגיאה בייבוא: {_e}")

    # ══════ Section B: הוספה ידנית ════════════════════════════════════════════
    st.markdown("""
<div dir="rtl" style="background:#f8fafc;border:1px solid #e2e8f0;border-right:3px solid #7c3aed;
     border-radius:8px;padding:10px 16px 6px;margin:14px 0 8px">
  <div style="font-size:12px;font-weight:800;color:#5b21b6;margin-bottom:2px">
    ➕ ב. הוספת מוצר ידנית
  </div>
  <div style="font-size:11px;color:#475569">
    נדל"ן, עו"ש, קריפטו, מוצרים פנסיוניים שאינם בדוח המסלקה
  </div>
</div>""", unsafe_allow_html=True)

    try:
        from portfolio_analysis.ui import _render_add_form
        from portfolio_analysis.models import STATE_KEY as _SK
        _render_add_form(list(case.all_holdings), df_long)
        # Sync pf_holdings → CaseStore if form added a product
        import streamlit as _st_inner
        _pf_h = _st_inner.session_state.get(_SK) or []
        # Use uid-based merge: any uid in pf_h not already in case → new product added
        _existing_uids = {h.get("uid","") for h in case.all_holdings}
        _new_in_pf = [h for h in _pf_h if h.get("uid","") not in _existing_uids]
        if _new_in_pf:
            _c2 = CaseStore.get()
            # Preserve imported holdings + add new manual products
            _merged = list(_c2.holdings_imported) + list(_c2.holdings_manual) + _new_in_pf
            _c2.holdings_manual     = [h for h in _pf_h if h.get("entry_mode","manual") == "manual"]
            _c2.holdings_normalized = _merged
            _c2.step_done[STEP_DATA_INTAKE] = True
            CaseStore.save(_c2)
            case = _c2
    except Exception as _add_err:
        st.warning(f"שגיאת טופס הוספה: {_add_err}")

    # ── Edit existing holdings ───────────────────────────────────────────────
    case = CaseStore.get()
    if case.all_holdings:
        with st.expander(
            f"✏️ ניהול מוצרים קיימים ({len(case.all_holdings)})", expanded=False
        ):
            try:
                from portfolio_analysis.ui import _render_edit_controls
                _render_edit_controls(list(case.all_holdings), df_long)
                case = CaseStore.get()
            except Exception as _ed_err:
                st.caption(f"שגיאת עריכה: {_ed_err}")

    # ══════ Continue CTA — explicit only, NO auto-advance ════════════════════
    case = CaseStore.get()
    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    if case.all_holdings:
        case.mark_step_done(STEP_DATA_INTAKE)
        CaseStore.save(case)
        st.markdown("""
<div dir="rtl" style="background:linear-gradient(135deg,#f0fdf4,#dcfce7);
     border:1.5px solid #86efac;border-radius:12px;padding:14px 18px;margin-top:10px">
  <div style="font-size:12px;font-weight:800;color:#065f46;margin-bottom:3px">
    ✅ נתוני התיק נקלטו — מוכן להמשך
  </div>
  <div style="font-size:11.5px;color:#047857">
    לחץ "המשך לתמונת מצב" לצפייה בניתוח המשוקלל של התיק כולו
  </div>
</div>""", unsafe_allow_html=True)
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        if st.button(
            "📊 המשך לתמונת מצב — שלב 3",
            key="intake_continue_btn",
            type="primary",
        ):
            # Explicit only — user must click
            st.session_state["client_wizard_step"] = STEP_SNAPSHOT
            st.rerun()
    else:
        st.info(
            "הוסף לפחות מוצר אחד (מסלקה או ידנית) כדי להמשיך.",
            icon="ℹ️",
        )

def _step_snapshot(case, df_long, engine: WorkflowEngine) -> None:
    """Step 3: Weighted current-state snapshot."""
    ok, reasons = engine.can_advance(STEP_SNAPSHOT)
    if not ok:
        _show_blockers(reasons)
        _back_btn(STEP_DATA_INTAKE)
        return

    # Compute snapshot from the existing engine
    from case_management.before_after_pipeline import compute_baseline
    built = compute_baseline(case, df_long)

    if not built:
        st.warning("לא ניתן לחשב snapshot — לחץ 'חשב baseline' בניתוח הפורטפוליו למטה.")
    else:
        st.success("✅ תמונת מצב חושבה")
        _render_snapshot_summary(case.current_snapshot)

    # Render the full client portfolio view
    try:
        from client_portfolio.ui import render_client_portfolio
        render_client_portfolio(df_long, case.active_product_type)
    except Exception as e:
        st.warning(f"תצוגת תיק: {e}")

    case = CaseStore.get()
    if case.current_snapshot:
        case.mark_step_done(STEP_SNAPSHOT)
        CaseStore.save(case)
        _next_cta("תמונת מצב מוכנה", "עבור לאופטימיזציה",
                  "🎯 המשך לאופטימיזציה", "snap_next", STEP_OPTIMIZATION)


def _step_optimize_header(case, engine: WorkflowEngine) -> None:
    """
    Step 4: Optimization — renders compact header + product selector.
    DOES NOT call st.stop(). Falls through to main render block.
    """
    ok, reasons = engine.can_advance(STEP_OPTIMIZATION)
    if not ok:
        _show_blockers(reasons)

    # Compact product type selector
    _WORLDS = ["קרנות השתלמות","פוליסות חיסכון","קרנות פנסיה","קופות גמל","גמל להשקעה"]
    cur_pt = st.session_state.get("product_type", case.active_product_type)
    st.markdown("**עולם מוצר:**")
    pt_cols = st.columns(len(_WORLDS), gap="small")
    for col, w in zip(pt_cols, _WORLDS):
        with col:
            if st.button(w.replace("קרנות ","").replace("קופות ",""),
                         key=f"opt_pt_{w}", use_container_width=True,
                         type="primary" if cur_pt==w else "secondary"):
                st.session_state["product_type"] = w
                case.active_product_type = w
                CaseStore.save(case)
                st.rerun()

    # Show selected alt status
    sc = case.selected_scenario
    if sc:
        st.success(f"✅ חלופה נבחרה: **{sc.label}** — {sc.advantage or 'ניתן להמשיך לשלב AI'}")
        _next_cta("אופטימיזציה הושלמה", "עבור להסברי AI",
                  "🤖 המשך לשלב 5 — הסברי AI", "opt_next", STEP_AI_REVIEW)


def _step_ai_review(case, engine: WorkflowEngine) -> None:
    """Step 5: AI Review — structured, grounded, editable."""
    ok, reasons = engine.can_advance(STEP_AI_REVIEW)
    if not ok:
        _show_blockers(reasons)
        _back_btn(STEP_OPTIMIZATION)
        return

    # Ensure before/after is computed before AI runs
    from case_management.before_after_pipeline import compute_proposed, compute_deltas
    if not case.proposed_snapshot and case.selected_scenario:
        compute_proposed(case)
        compute_deltas(case)
        CaseStore.save(case)

    case = CaseStore.get()
    _render_before_after_summary(case)

    st.markdown("---")
    st.markdown("### 🤖 הסברי AI ואישור")
    st.caption(
        "AI מסביר את ההיגיון של השינויים על בסיס הנתונים בלבד. "
        "אין ייעוץ פיננסי. אין המצאת עובדות מספריות."
    )

    ai = case.ai_review
    _secs = st.session_state.get("final_report_sections", {})
    _has_ai = bool(_secs.get("executive_summary","").strip()) or (ai and ai.is_complete())

    if not _has_ai:
        # Trigger AI generation
        sc  = case.selected_scenario
        bl  = case.current_snapshot
        tgts = case.optimizer_targets

        if not sc:
            st.warning("חסר: חלופה נבחרת. חזור לשלב האופטימיזציה.")
            return

        bl_text = ""
        if bl:
            bl_text = (
                f"מניות={bl.stocks_pct:.1f}% חו\"ל={bl.foreign_pct:.1f}% "
                f"מט\"ח={bl.fx_pct:.1f}% לא-סחיר={bl.illiquid_pct:.1f}% "
                f"שארפ={bl.sharpe:.2f} עלות={bl.cost_pct:.2f}%"
            ) if bl.stocks_pct is not None and bl.stocks_pct == bl.stocks_pct else ""

        if st.button("🤖 הפק הסברי AI", key="wiz_gen_ai_v3", type="primary"):
            try:
                from institutional_strategy_analysis.ai_analyst import (
                    _call_claude, _external_guidance_block
                )
                import re
                guidance = _external_guidance_block()
                deltas_text = ""
                if case.exposure_deltas:
                    deltas_text = " · ".join(
                        f"{d.label_he}: {d.before:.1f}%→{d.after:.1f}% ({d.delta_pp:+.1f}pp)"
                        for d in case.exposure_deltas
                        if d.before is not None and d.after is not None
                    )

                prompt = (
                    f"mode: planning\\n"
                    f"עולם מוצר: {case.active_product_type}\\n"
                    f"חלופה נבחרת: {sc.label}\\n"
                    f"מנהלים: {sc.managers}\\n"
                    f"יתרון מוצהר: {sc.advantage}\\n"
                    f"מצב נוכחי: {bl_text or 'חסר'}\\n"
                    f"שינויי חשיפה: {deltas_text or 'חסר'}\\n"
                    f"יעדים: {tgts}\\n\\n"
                    f"הנחיות ממסמך חיצוני:\\n{guidance}\\n\\n"
                    "כתוב 4 סעיפים בסדר הזה בדיוק, בעברית, כל אחד עם כותרת בסוגריים מרובעים:\\n"
                    "[1. ניתוח וטיעון מקצועי — ליועץ]\\n"
                    "[2. הסבר ללקוח — ברור ונגיש]\\n"
                    "[3. שיקולים ומקבילות]\\n"
                    "[4. הנחות ופערי נתונים]\\n\\n"
                    "כללים: אל תמציא נתונים. אל תשתמש בנתונים שאינם בקלט. "
                    "אל תיתן ייעוץ מחייב. טון: מקצועי ומאוזן."
                )
                with st.spinner("מפיק הסברי AI..."):
                    raw, err = _call_claude(prompt, max_tokens=2500)
                if err:
                    st.error(f"שגיאת AI: {err}")
                else:
                    def _extract(text, n):
                        m = re.search(rf"\\[{n}\\..*?\\](.*?)(?=\\[\\d\\.|$)", text, re.DOTALL)
                        return m.group(1).strip() if m else ""

                    case = CaseStore.get()
                    case.ai_review = type(case.ai_review or __import__('case_management').AIReview)()
                    from case_management import AIReview as AIR
                    case.ai_review = AIR(
                        advisor_rationale  = _extract(raw, "1"),
                        client_explanation = _extract(raw, "2"),
                        trade_offs         = _extract(raw, "3"),
                        assumptions_text   = _extract(raw, "4"),
                        executive_summary  = _extract(raw, "1"),
                        change_advantages  = _extract(raw, "3"),
                        final_summary      = _extract(raw, "2"),
                    )
                    case.step_done[STEP_AI_REVIEW] = True
                    CaseStore.save(case)
                    st.success("✅ הסברי AI נוצרו")
                    st.rerun()
            except Exception as ai_err:
                st.error(f"שגיאת AI: {ai_err}")
    else:
        # Show editable sections
        st.success("✅ הסברי AI קיימים — ניתן לערוך ולאשר")
        _tone = st.radio("טון", ["professional","simple","persuasive"],
                         format_func=lambda x: {"professional":"מקצועי","simple":"נגיש","persuasive":"שכנועי"}[x],
                         horizontal=True, key="ai_tone")

        _editable = {}
        for key, label in [
            ("executive_summary",   "1. תקציר מנהלים"),
            ("current_weaknesses",  "2. חולשות התיק הנוכחי"),
            ("change_advantages",   "3. יתרונות השינויים"),
            ("risks_considerations","4. שיקולים ואיזונים"),
            ("final_summary",       "5. סיכום סופי"),
        ]:
            default = _secs.get(key,"") or (getattr(case.ai_review, key.replace("risks_considerations","risks"), "") if case.ai_review else "")
            _editable[key] = st.text_area(label, value=default, height=110, key=f"ai_edit_{key}")

        col_save, col_regen, _ = st.columns([1, 1, 4])
        with col_save:
            if st.button("💾 שמור", key="ai_save_v3", type="primary"):
                st.session_state["final_report_sections"] = _editable
                case = CaseStore.get()
                if not case.ai_review:
                    from case_management import AIReview as AIR2
                    case.ai_review = AIR2()
                case.ai_review.executive_summary  = _editable.get("executive_summary","")
                case.ai_review.change_advantages  = _editable.get("change_advantages","")
                case.ai_review.risks              = _editable.get("risks_considerations","")
                case.ai_review.final_summary      = _editable.get("final_summary","")
                case.step_done[STEP_AI_REVIEW]    = True
                CaseStore.save(case)
                st.success("נשמר ✅")

        with col_regen:
            if st.button("🔄 הפק מחדש", key="ai_regen"):
                st.session_state.pop("final_report_sections", None)
                case = CaseStore.get(); case.ai_review = None
                CaseStore.save(case); st.rerun()

        if case.ai_review and case.ai_review.is_complete():
            _next_cta("הסברי AI אושרו", "בנה את חבילת לפני/אחרי",
                      "⚖️ המשך לשלב לפני/אחרי", "ai_next", STEP_BEFORE_AFTER)


def _step_before_after(case, df_long, engine: WorkflowEngine) -> None:
    """Step 6: Before/After package build + review."""
    ok, reasons = engine.can_advance(STEP_BEFORE_AFTER)
    if not ok:
        _show_blockers(reasons)
        _back_btn(STEP_AI_REVIEW)
        return

    # Run full pipeline
    from case_management.before_after_pipeline import run_full_pipeline
    run_full_pipeline(case, df_long)
    case = CaseStore.get()

    if not case.has_before_after():
        st.warning("⚠️ לא ניתן לבנות חבילת לפני/אחרי — חסרים נתוני baseline או חלופה נבחרת.")
        _back_btn(STEP_OPTIMIZATION)
        return

    st.markdown("### ⚖️ חבילת לפני / אחרי")
    _render_before_after_table(case)

    st.markdown("---")
    # Summary text
    sc = case.selected_scenario
    if sc:
        st.markdown(f"**חלופה נבחרת:** {sc.label} · {sc.managers}")
        if sc.advantage:
            st.info(f"🎯 {sc.advantage}")

    # Assumptions & missing data
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**הנחות:**")
        assumptions_new = st.text_area("", value="\n".join(case.assumptions), height=80, key="ba_assumptions", label_visibility="collapsed")
    with col2:
        st.markdown("**נתונים חסרים / הערות:**")
        notes_new = st.text_area("", value="\n".join(case.missing_data_notes), height=80, key="ba_notes", label_visibility="collapsed")

    if st.button("💾 שמור ואשר חבילה", key="ba_save", type="primary"):
        case = CaseStore.get()
        case.assumptions        = [l.strip() for l in assumptions_new.split("\n") if l.strip()]
        case.missing_data_notes = [l.strip() for l in notes_new.split("\n") if l.strip()]
        case.mark_step_done(STEP_BEFORE_AFTER)
        CaseStore.save(case)
        st.success("✅ חבילת לפני/אחרי נשמרה")
        _next_cta("חבילה אושרה", "עבור לייצוא",
                  "📋 המשך לשלב ייצוא", "ba_next", STEP_EXPORT)


def _step_export(case, engine: WorkflowEngine) -> None:
    """Step 7: Export — build bundle and download."""
    ok, reasons = engine.can_advance(STEP_EXPORT)
    if not ok:
        _show_blockers(reasons)
        _back_btn(STEP_BEFORE_AFTER)
        return

    # Build the export bundle
    from case_management.before_after_pipeline import build_export_bundle
    import json

    bundle = build_export_bundle(case)
    case.export_payload = bundle
    case.mark_step_done(STEP_EXPORT)
    CaseStore.save(case)

    # Export readiness summary
    st.markdown("### 📋 חבילת לקוח מוכנה לייצוא")
    flags = engine.get_flags()
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("מוצרים", len(case.all_holdings) or "—")
    c2.metric("חשיפות", "✅" if flags.has_snapshot else "⚠️")
    c3.metric("AI", "✅" if flags.has_ai_review else "⚠️ חסר")
    c4.metric("לפני/אחרי", "✅" if flags.has_before_after else "⚠️")

    # Warnings
    for w in flags.warnings:
        st.warning(f"⚠️ {w}")

    # Before/after summary
    _render_before_after_table(case)
    st.markdown("---")

    bundle_json = json.dumps(bundle, ensure_ascii=False, indent=2)
    ai = case.ai_review

    # Download options
    d1, d2, d3 = st.columns(3)
    with d1:
        st.download_button(
            "📦 חבילת Notebook (JSON)",
            data=bundle_json.encode("utf-8"),
            file_name=f"case_{case.case_id}.json",
            mime="application/json",
            key="export_dl_json",
            help="schema v3.1 · אין NaN · מוכן ל-NotebookLM",
        )
    with d2:
        txt_lines = [f"דוח לקוח: {case.client_name}", ""]
        if ai:
            txt_lines += ["=== ניתוח מקצועי ===", ai.advisor_rationale or ai.executive_summary, "",
                          "=== הסבר ללקוח ===", ai.client_explanation or ai.final_summary, "",
                          "=== שיקולים ===", ai.trade_offs or ai.risks, ""]
        txt_lines += ["=== הנחות ==="] + case.assumptions
        st.download_button(
            "📄 טקסט מלא (.txt)",
            data="\n".join(txt_lines).encode("utf-8"),
            file_name=f"report_{case.case_id}.txt",
            mime="text/plain",
            key="export_dl_txt",
        )
    with d3:
        st.caption(f"schema v3.1 · case {case.case_id} · {bundle['data_completeness']}")

    st.balloons()


# ── UI helpers ────────────────────────────────────────────────────────────────

def _render_progress_bar(status: dict, active_step: int) -> None:
    nodes = []
    for s in range(1, 8):
        st_obj: StepStatus = status[s]
        cls   = "done" if st_obj.done else ("active" if st_obj.active else ("blocked" if st_obj.blocked else ""))
        icon  = "✓" if st_obj.done else st_obj.icon
        nodes.append(
            f'<div class="wiz-node {cls}">'
            f'<div class="wiz-dot">{icon}</div>'
            f'<div class="wiz-lbl">{st_obj.label}</div>'
            f'</div>'
        )
    st.markdown(
        '<div class="wiz-bar"><div class="wiz-bar-mode">מסלול לקוח</div>'
        '<div class="wiz-nodes">' + "".join(nodes) + '</div></div>',
        unsafe_allow_html=True
    )
    # Compact navigation buttons
    nav_cols = st.columns(8, gap="small")
    for i, s in enumerate(range(1, 8)):
        with nav_cols[i]:
            t = "primary" if s == active_step else "secondary"
            if st.button(str(s), key=f"wiz_nav_p3_{s}", type=t, use_container_width=True,
                         help=STEP_LABELS.get(s,"")):
                ok, reasons = status[s].done or True, []
                if not status[s].blocked:
                    st.session_state["client_wizard_step"] = s
                    st.rerun()
    with nav_cols[7]:
        if st.button("🏠", key="wiz_home_p3", use_container_width=True):
            st.session_state["app_page"] = "home"
            st.session_state["app_mode"] = "home"
            st.rerun()


def _render_snapshot_summary(snap) -> None:
    if not snap: return
    import math
    def _fmt(v): return f"{v:.1f}%" if v and not math.isnan(v) else "—"
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("מניות",    _fmt(snap.stocks_pct))
    c2.metric('חו"ל',     _fmt(snap.foreign_pct))
    c3.metric('מט"ח',     _fmt(snap.fx_pct))
    c4.metric("לא-סחיר", _fmt(snap.illiquid_pct))
    c5.metric("שארפ",    f"{snap.sharpe:.2f}" if snap.sharpe and not math.isnan(snap.sharpe) else "—")


def _render_before_after_summary(case) -> None:
    cur = case.current_snapshot
    prp = case.proposed_snapshot
    if not cur and not prp: return
    import math

    st.markdown("#### 📊 לפני / אחרי")
    if case.exposure_deltas:
        cols = st.columns(len(case.exposure_deltas))
        for col, d in zip(cols, case.exposure_deltas):
            a_s = f"{d.after:.1f}" if d.after is not None else "—"
            d_s = f"{d.delta_pp:+.1f}pp" if d.delta_pp is not None else None
            col.metric(d.label_he, a_s, delta=d_s)
    else:
        _render_snapshot_summary(cur)


def _render_before_after_table(case) -> None:
    import math
    if not case.exposure_deltas:
        _render_before_after_summary(case)
        return

    rows = []
    for d in case.exposure_deltas:
        b = f"{d.before:.1f}%" if d.before is not None else "—"
        a = f"{d.after:.1f}%"  if d.after  is not None else "—"
        dp= f"{d.delta_pp:+.1f}pp" if d.delta_pp is not None else "—"
        dir_icon = {"up":"↑","down":"↓","neutral":"↔","unknown":"?"}.get(d.direction,"?")
        rows.append({"מדד": d.label_he, "לפני": b, "אחרי": a, "שינוי": dp, "כיוון": dir_icon})

    import pandas as pd
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _next_cta(title, desc, btn_label, btn_key, target_step) -> None:
    st.markdown(f"""
<div class="wiz-next">
  <div class="wiz-next-title">✅ {title}</div>
  <div class="wiz-next-desc">{desc}</div>
</div>""", unsafe_allow_html=True)
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
    if st.button(btn_label, key=btn_key, type="primary"):
        st.session_state["client_wizard_step"] = target_step
        st.rerun()


def _show_blockers(reasons: list) -> None:
    if reasons:
        st.markdown(
            '<div class="wiz-blocker">' +
            "<br>".join(f"⚠️ {r}" for r in reasons) +
            '</div>', unsafe_allow_html=True
        )


def _back_btn(target_step: int) -> None:
    if st.button(f"← חזור לשלב {target_step}", key=f"back_{target_step}"):
        st.session_state["client_wizard_step"] = target_step
        st.rerun()
