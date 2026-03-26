# -*- coding: utf-8 -*-
"""
client_portfolio/ui.py
───────────────────────
Standalone Streamlit UI for "ניתוח תיק לקוח".
Rendered as an st.expander — zero interference with the rest of the app.

Entry point (one line in streamlit_app.py):
    from client_portfolio.ui import render_client_portfolio
    render_client_portfolio(df_long, product_type)

All session-state keys are prefixed  "cp_"  to avoid any collision.
"""
from __future__ import annotations

import math
from typing import Optional

import pandas as pd
import streamlit as st

# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_plotly(fig, key: str) -> None:
    try:
        st.plotly_chart(fig, use_container_width=True, key=key)
    except TypeError:
        st.plotly_chart(fig)


def _fmt(v, fmt="{:.1f}%"):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    try:
        return fmt.format(float(v))
    except Exception:
        return str(v)


def _ils(v: float) -> str:
    if not v or math.isnan(v):
        return "—"
    if v >= 1_000_000:
        return f"₪{v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"₪{v/1_000:.0f}K"
    return f"₪{v:.0f}"


# ── Pull holdings from portfolio_analysis session state ───────────────────────

def _get_pf_holdings() -> list[dict]:
    """Pull holdings from the portfolio_analysis module's session state."""
    return st.session_state.get("pf_holdings", [])


# ── Enrich with cost column ───────────────────────────────────────────────────

def _enrich_costs(holdings: list[dict]) -> list[dict]:
    """
    Add annual_cost_pct from cp_costs session state (user-entered per product).
    """
    costs = st.session_state.get("cp_costs", {})
    enriched = []
    for h in holdings:
        hc = dict(h)
        hc["annual_cost_pct"] = costs.get(h["uid"], None)
        enriched.append(hc)
    return enriched


# ── Cost input UI ─────────────────────────────────────────────────────────────

def _render_cost_inputs(holdings: list[dict]) -> None:
    if not holdings:
        return
    st.markdown("#### 8. דמי ניהול שנתיים (אופציונלי)")
    st.caption("הזן דמי ניהול לכל מוצר (%) לחישוב עלות משוקללת. שדה ריק = לא ידוע.")
    costs = st.session_state.get("cp_costs", {})
    changed = False
    cols = st.columns(3)
    for i, h in enumerate(holdings):
        uid   = h["uid"]
        label = f"{h.get('provider','')} | {h.get('product_name','')}"
        val   = costs.get(uid, 0.0) or 0.0
        with cols[i % 3]:
            new_val = st.number_input(label, 0.0, 5.0, float(val), step=0.01,
                                      format="%.2f", key=f"cp_cost_{uid}")
            if new_val != val:
                costs[uid] = new_val
                changed = True
    if changed:
        st.session_state["cp_costs"] = costs


# ── Main entry point ──────────────────────────────────────────────────────────

def render_client_portfolio(df_long: pd.DataFrame, product_type: str) -> None:
    """
    Render the client portfolio analysis module as a top-level expander.
    Reads holdings from portfolio_analysis module (pf_holdings).
    """
    with st.expander("📊 ניתוח תיק לקוח", expanded=False):

        holdings_raw = _get_pf_holdings()
        if not holdings_raw:
            st.info(
                "💡 **כדי להפעיל ניתוח זה**, ייבא פורטפוליו בחלק "
                "**💼 ניתוח פורטפוליו נוכחי** שמתחת.",
                icon="📂",
            )
            return

        holdings = _enrich_costs(holdings_raw)
        import pandas as pd
        df = pd.DataFrame(holdings)
        for col in ["amount", "equity_pct", "foreign_pct", "fx_pct",
                    "illiquid_pct", "sharpe"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "excluded" not in df.columns:
            df["excluded"] = False

        from client_portfolio.charts import compute_totals
        totals = compute_totals(df)

        # ── Client name input ─────────────────────────────────────────────
        client_name = st.text_input(
            "שם הלקוח (לכותרת הדוח)",
            value=st.session_state.get("cp_client_name", ""),
            key="cp_client_name_input",
            placeholder="ישראל ישראלי",
        )
        st.session_state["cp_client_name"] = client_name

        # ── KPI strip ──────────────────────────────────────────────────────
        k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
        k1.metric("סך נכסים",       _ils(totals.get("total", 0)))
        k2.metric("מוצרים",          str(totals.get("n_products", 0)))
        k3.metric("מנהלים",          str(totals.get("n_managers", 0)))
        k4.metric("מניות (משוקלל)", _fmt(totals.get("equity")))
        k5.metric('חו"ל (משוקלל)',   _fmt(totals.get("foreign")))
        k6.metric('מט"ח (משוקלל)',   _fmt(totals.get("fx")))
        k7.metric("לא סחיר",         _fmt(totals.get("illiquid")))

        st.markdown("---")

        # ── Tabs ───────────────────────────────────────────────────────────
        tabs = st.tabs([
            "📊 גרפים",
            "💰 עלויות",
            "📋 טבלה מלאה",
            "📥 הורדת דוחות",
        ])

        with tabs[0]:
            _render_charts(df, totals)

        with tabs[1]:
            _render_cost_inputs(holdings_raw)
            # Re-enrich after cost input
            holdings = _enrich_costs(holdings_raw)
            df_cost = pd.DataFrame(holdings)
            for col in ["amount", "annual_cost_pct"]:
                if col in df_cost.columns:
                    df_cost[col] = pd.to_numeric(df_cost[col], errors="coerce")
            if "excluded" not in df_cost.columns:
                df_cost["excluded"] = False
            from client_portfolio.charts import chart_costs
            fig_cost = chart_costs(df_cost)
            if fig_cost.data:
                _safe_plotly(fig_cost, key="cp_costs_chart")
            else:
                st.info("הזן דמי ניהול בשדות למעלה לצפייה בגרף עלויות.")

        with tabs[2]:
            _render_full_table(df, totals)

        with tabs[3]:
            _render_downloads(df, totals, client_name, holdings_raw)


def _render_charts(df: pd.DataFrame, totals: dict) -> None:
    """Render portfolio analysis charts."""
    from client_portfolio.charts import (
        chart_by_manager, chart_stocks_bonds, chart_foreign_domestic,
        chart_fx_ils, chart_asset_breakdown, chart_annuity_capital,
    )

    # Row 1: manager donut + stocks/bonds/illiquid
    c1, c2 = st.columns(2)
    with c1:
        _safe_plotly(chart_by_manager(df), "cp_mgr")
    with c2:
        _safe_plotly(chart_stocks_bonds(df), "cp_sb")

    # Row 2: foreign/domestic + FX/ILS
    c3, c4 = st.columns(2)
    with c3:
        _safe_plotly(chart_foreign_domestic(df), "cp_fd")
    with c4:
        _safe_plotly(chart_fx_ils(df), "cp_fx")

    # Row 3: product-type donut + annuity vs capital
    st.markdown("---")
    c5, c6 = st.columns(2)
    with c5:
        _safe_plotly(chart_asset_breakdown(df), "cp_ab")
    with c6:
        # Annuity vs capital: auto from product_type, or manual slider
        has_product_type = ("product_type" in df.columns and
                            df["product_type"].notna().any() and
                            df["product_type"].ne("").any())
        if has_product_type:
            _safe_plotly(chart_annuity_capital(df), "cp_ac")
            ann_pct = None
        else:
            st.caption("ℹ️ לא זוהה סוג מוצר — הזן אחוז קצבה ידנית:")
            ann_pct = st.slider("% קצבה בתיק", 0, 100,
                                int(st.session_state.get("cp_ann_pct", 30)),
                                key="cp_ann_slider")
            st.session_state["cp_ann_pct"] = ann_pct
            _safe_plotly(chart_annuity_capital(df, manual_annuity_pct=ann_pct), "cp_ac")


def _render_full_table(df: pd.DataFrame, totals: dict) -> None:
    active = df[~df.get("excluded", pd.Series([False]*len(df))).astype(bool)]
    if active.empty:
        st.info("אין מוצרים להצגה.")
        return

    total_amt = active["amount"].sum()
    disp = active.copy()
    disp["משקל %"] = (disp["amount"] / total_amt * 100).round(1) if total_amt > 0 else 0
    disp = disp.rename(columns={
        "provider": "גוף", "product_name": "מוצר", "track": "מסלול",
        "product_type": "סוג", "amount": "סכום",
        "equity_pct": "מניות %", "foreign_pct": 'חו"ל %',
        "fx_pct": 'מט"ח %', "illiquid_pct": "לא סחיר %",
        "sharpe": "שארפ",
    })
    show_cols = [c for c in ["גוף", "מוצר", "מסלול", "סוג", "סכום", "משקל %",
                              "מניות %", 'חו"ל %', 'מט"ח %', "לא סחיר %", "שארפ"]
                 if c in disp.columns]
    st.dataframe(disp[show_cols].reset_index(drop=True),
                 use_container_width=True, hide_index=True)


def _render_downloads(df: pd.DataFrame, totals: dict,
                      client_name: str, holdings_raw: list[dict]) -> None:
    from client_portfolio.report_builder import build_html_report, build_notebook

    st.markdown("#### הורדת דוחות")

    # Enrich costs
    holdings_cost = _enrich_costs(holdings_raw)
    df_full = pd.DataFrame(holdings_cost)
    for col in ["amount","equity_pct","foreign_pct","fx_pct","illiquid_pct","sharpe","annual_cost_pct"]:
        if col in df_full.columns:
            df_full[col] = pd.to_numeric(df_full[col], errors="coerce")
    if "excluded" not in df_full.columns:
        df_full["excluded"] = False

    from client_portfolio.charts import compute_totals
    totals_full = compute_totals(df_full)

    dc1, dc2, dc3 = st.columns(3)

    # HTML report
    with dc1:
        html_bytes = build_html_report(df_full, client_name, totals_full)
        st.download_button(
            "📄 דוח HTML מעוצב",
            data=html_bytes,
            file_name=f"portfolio_report_{client_name or 'client'}.html",
            mime="text/html",
            key="cp_dl_html",
            help="דוח מעוצב שניתן להדפיס או לפתוח בדפדפן",
        )

    # Jupyter notebook
    with dc2:
        nb_bytes = build_notebook(df_full, client_name, totals_full)
        st.download_button(
            "📓 Jupyter Notebook",
            data=nb_bytes,
            file_name=f"portfolio_analysis_{client_name or 'client'}.ipynb",
            mime="application/json",
            key="cp_dl_nb",
            help="נוטבוק מוכן להפעלה — פתח ב-Jupyter / Google Colab ולחץ Run All",
        )

    # CSV
    with dc3:
        csv = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        st.download_button(
            "⬇️ CSV",
            data=csv,
            file_name="portfolio_data.csv",
            mime="text/csv",
            key="cp_dl_csv",
        )

    st.markdown("---")
    st.markdown("""
**🚀 כיצד להשתמש בנוטבוק:**
1. הורד את הקובץ `.ipynb`
2. פתח ב-[Jupyter Lab](https://jupyter.org) / [VS Code](https://code.visualstudio.com) / [Google Colab](https://colab.research.google.com)
3. `Run All` — כל הגרפים ייוצרו אוטומטית
4. ייצא ל-PDF / HTML לצורך מצגת ללקוח

**📎 העתקה ל-Google Colab:**
- [Colab](https://colab.research.google.com) → `File → Upload notebook` → בחר את הקובץ
""")


# ── Full-page mode (called when product_type == "תיק לקוח") ──────────────────

def render_client_portfolio_page(df_long) -> None:
    """
    Full-page client portfolio UI — replaces the optimizer entirely.
    Called from streamlit_app.py when product_type == "תיק לקוח".
    """
    import streamlit as st
    # Import helpers from portfolio_analysis module
    from portfolio_analysis.ui import (
        _render_add_form, _render_edit_controls, _render_whatif,
    )
    from portfolio_analysis.models import import_from_session, set_holdings

    st.markdown("""
<div style='background:linear-gradient(135deg,#1F3A5F 0%,#3A7AFE 100%);
     border-radius:14px;padding:20px 28px;margin-bottom:18px;color:#fff'>
  <div style='font-size:22px;font-weight:900'>📊 ניתוח תיק לקוח</div>
  <div style='font-size:13px;opacity:0.8;margin-top:4px'>
    העלה דוח מסלקה · הוסף מוצרים ידנית · קבל ניתוח מקיף · הפק דוח מקצועי
  </div>
</div>
""", unsafe_allow_html=True)

    holdings_raw = _get_pf_holdings()

    # ── Step 1: Import / Add holdings ────────────────────────────────────
    with st.expander(
        f"{'✅' if holdings_raw else '📂'} שלב 1 — ייבוא פורטפוליו "
        f"({'%d מוצרים' % len(holdings_raw) if holdings_raw else 'ריק'})",
        expanded=not bool(holdings_raw),
    ):
        # ── File uploader (moved here from advanced settings) ─────────────
        st.markdown("##### 📂 העלאת דוח מסלקה (XLSX)")
        uploaded = st.file_uploader(
            'דוח מסלקה (XLSX/XLS)', type=["xlsx","xls"],
            key="cppage_upload", label_visibility="collapsed",
        )
        if uploaded:
            try:
                from streamlit_app import parse_clearing_report, _compute_baseline_from_holdings
            except Exception:
                # fallback: import directly from parent scope
                import importlib, sys
                # parse_clearing_report lives in streamlit_app — access via session workaround
                parse_clearing_report = st.session_state.get("_parse_clearing_fn")

            # Direct inline parser to avoid cross-module import issues
            if uploaded:
                raw_bytes = uploaded.read()
                try:
                    import io, math, re
                    import pandas as _pd
                    import numpy as _np
                    AMOUNT_ALIASES  = ["יתרה","ערך","סכום","balance","amount","שווי"]
                    FUND_ALIASES    = ["שם הקרן","קרן","שם מוצר","fund","product","שם הקופה","שם הגוף"]
                    MANAGER_ALIASES = ["מנהל","גוף מנהל","בית השקעות","manager","provider"]
                    TRACK_ALIASES   = ["מסלול","track","שם מסלול"]

                    def _to_f(v):
                        try:
                            s = str(v).replace(",","").replace("₪","").strip()
                            return float(s)
                        except Exception:
                            return float("nan")

                    xls = _pd.ExcelFile(io.BytesIO(raw_bytes))
                    all_recs = []
                    for sheet in xls.sheet_names:
                        try:
                            df_s = _pd.read_excel(xls, sheet_name=sheet, header=None)
                        except Exception:
                            continue
                        if df_s.empty or df_s.shape[0] < 2:
                            continue
                        header_idx = None
                        for i in range(min(10, len(df_s))):
                            row_vals = [str(v).strip().lower() for v in df_s.iloc[i].tolist()]
                            matches = sum(1 for v in row_vals
                                if any(a.lower() in v for a in AMOUNT_ALIASES+FUND_ALIASES+MANAGER_ALIASES))
                            if matches >= 2:
                                header_idx = i; break
                        if header_idx is None:
                            continue
                        dc = df_s.iloc[header_idx:].copy().reset_index(drop=True)
                        dc.columns = [str(c).strip() for c in dc.iloc[0].tolist()]
                        dc = dc.iloc[1:].reset_index(drop=True)
                        def _fc(aliases):
                            for col in dc.columns:
                                if any(a.lower() in col.lower() for a in aliases):
                                    return col
                            return None
                        fund_col    = _fc(FUND_ALIASES)
                        manager_col = _fc(MANAGER_ALIASES)
                        amount_col  = _fc(AMOUNT_ALIASES)
                        track_col   = _fc(TRACK_ALIASES)
                        if not (fund_col or manager_col) or not amount_col:
                            continue
                        for _, row in dc.iterrows():
                            fn = str(row.get(fund_col,"") or "").strip() if fund_col else ""
                            mn = str(row.get(manager_col,"") or "").strip() if manager_col else ""
                            tn = str(row.get(track_col,"") or "").strip() if track_col else ""
                            av = _to_f(row.get(amount_col, _np.nan))
                            if not fn and not mn: continue
                            if math.isnan(av) or av <= 0: continue
                            all_recs.append({"fund": fn or mn, "manager": mn or fn,
                                             "track": tn, "amount": av})
                    if all_recs:
                        total = sum(r["amount"] for r in all_recs)
                        for r in all_recs:
                            r["weight_pct"] = round(r["amount"]/total*100, 2) if total>0 else 0.0
                        st.session_state["portfolio_holdings"] = all_recs
                        st.session_state["portfolio_total"]    = total
                        st.session_state["portfolio_managers"] = list({r["manager"] for r in all_recs})
                        st.success(f"✅ טעון: {len(all_recs)} קרנות, ₪{total:,.0f}")
                        holdings_raw = _get_pf_holdings()  # refresh
                    else:
                        st.error("לא נמצאו נתונים בקובץ. ודא שהקובץ הוא דוח מסלקה עם עמודות שם קרן/מנהל וסכום.")
                except Exception as _e:
                    st.error(f"שגיאה בפרסור הקובץ: {_e}")

        st.markdown("---")

        # ── Import from already-parsed session state ──────────────────────
        raw_import = st.session_state.get("portfolio_holdings") or []
        if raw_import:
            existing_keys = {(h["provider"].lower(), h["product_name"].lower()) for h in holdings_raw}
            new_ct = sum(1 for r in raw_import
                         if (str(r.get("manager","")).lower(), str(r.get("fund","")).lower())
                         not in existing_keys)
            if new_ct > 0:
                if st.button(f"📥 ייבא {new_ct} מוצרים לניתוח", key="cppage_import", type="primary"):
                    added = import_from_session(st, df_long, "קרנות השתלמות")
                    if added:
                        st.success(f"✅ {added} מוצרים יובאו")
                        st.rerun()
            else:
                st.success(f"✅ {len(raw_import)} מוצרים מיובאים לניתוח")

        st.markdown("---")
        # Manual add form
        _render_add_form(holdings_raw, df_long)

    if not holdings_raw:
        st.info("💡 העלה דוח מסלקה בהגדרות המתקדמות (⚙️) או הוסף מוצרים ידנית למעלה.")
        return

    # ── Step 2: Edit & manage ─────────────────────────────────────────────
    with st.expander("✏️ שלב 2 — ניהול ועריכת מוצרים", expanded=False):
        if _render_edit_controls(holdings_raw, df_long):
            set_holdings(st, holdings_raw)
            st.rerun()

    # ── Step 3: Analysis ──────────────────────────────────────────────────
    holdings = _enrich_costs(holdings_raw)
    df = pd.DataFrame(holdings)
    for col in ["amount","equity_pct","foreign_pct","fx_pct","illiquid_pct","sharpe"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "excluded" not in df.columns:
        df["excluded"] = False

    from client_portfolio.charts import compute_totals
    totals = compute_totals(df)

    # Client name
    col_name, col_spacer = st.columns([2, 4])
    with col_name:
        client_name = st.text_input("שם הלקוח", value=st.session_state.get("cp_client_name",""),
                                     key="cppage_client_name", placeholder="ישראל ישראלי")
        st.session_state["cp_client_name"] = client_name

    # KPIs
    k1,k2,k3,k4,k5,k6,k7 = st.columns(7)
    k1.metric("סך נכסים",       _ils(totals.get("total",0)))
    k2.metric("מוצרים",          str(totals.get("n_products",0)))
    k3.metric("מנהלים",          str(totals.get("n_managers",0)))
    k4.metric("מניות (משוקלל)", _fmt(totals.get("equity")))
    k5.metric('חו"ל (משוקלל)',   _fmt(totals.get("foreign")))
    k6.metric('מט"ח (משוקלל)',   _fmt(totals.get("fx")))
    k7.metric("לא סחיר",         _fmt(totals.get("illiquid")))

    st.markdown("---")

    # ── 1. Summary table — first thing the user sees ─────────────────────
    st.markdown("""
<div style='display:flex;align-items:center;gap:10px;margin:4px 0 14px 0;direction:rtl'>
  <div style='width:4px;height:24px;background:linear-gradient(180deg,#1F3A5F,#3A7AFE);
       border-radius:3px;flex-shrink:0'></div>
  <div style='font-size:17px;font-weight:800;color:#1F3A5F'>📋 סיכום תיק</div>
</div>""", unsafe_allow_html=True)
    _render_full_table(df, totals)

    st.markdown("---")

    # ── 2. Charts ─────────────────────────────────────────────────────────
    st.markdown("""
<div style='display:flex;align-items:center;gap:10px;margin:4px 0 14px 0;direction:rtl'>
  <div style='width:4px;height:24px;background:linear-gradient(180deg,#1F3A5F,#3A7AFE);
       border-radius:3px;flex-shrink:0'></div>
  <div style='font-size:17px;font-weight:800;color:#1F3A5F'>📈 ניתוח גרפי</div>
</div>""", unsafe_allow_html=True)
    _render_charts(df, totals)

    # Costs chart (shown only if cost data entered)
    holdings_cost = _enrich_costs(holdings_raw)
    df_cost = pd.DataFrame(holdings_cost)
    for col in ["amount","annual_cost_pct"]:
        if col in df_cost.columns:
            df_cost[col] = pd.to_numeric(df_cost[col], errors="coerce")
    if "excluded" not in df_cost.columns:
        df_cost["excluded"] = False
    from client_portfolio.charts import chart_costs
    fc = chart_costs(df_cost)
    if fc.data:
        st.markdown("""
<div style='display:flex;align-items:center;gap:10px;margin:12px 0 14px 0;direction:rtl'>
  <div style='width:4px;height:24px;background:linear-gradient(180deg,#1F3A5F,#3A7AFE);
       border-radius:3px;flex-shrink:0'></div>
  <div style='font-size:17px;font-weight:800;color:#1F3A5F'>💰 ניתוח עלויות</div>
</div>""", unsafe_allow_html=True)
        _safe_plotly(fc, "cppage_costs_main")

    st.markdown("---")

    # ── 3. Export — prominent, at the bottom ─────────────────────────────
    st.markdown("""
<div style='background:linear-gradient(135deg,#1F3A5F 0%,#3A7AFE 100%);
border-radius:12px;padding:20px 28px;margin:8px 0 16px 0;direction:rtl'>
  <div style='color:#fff;font-size:18px;font-weight:900;margin-bottom:4px'>
    📥 הפקת דוחות ויצוא
  </div>
  <div style='color:#93c5fd;font-size:12px'>
    דוח HTML מעוצב · Jupyter Notebook · NotebookLM Package · CSV
  </div>
</div>
""", unsafe_allow_html=True)
    _render_downloads_page(df, totals, client_name, holdings_raw)

    # ── Additional tabs for editing and what-if ───────────────────────────
    st.markdown("---")
    with st.expander("✏️ עריכת מוצרים ו-What-If", expanded=False):
        t_edit, t_costs2, t_whatif = st.tabs(["✏️ עריכה", "💰 עלויות", "🔀 What-If"])
        with t_edit:
            pass  # edit controls rendered in step 2 above
        with t_costs2:
            _render_cost_inputs(holdings_raw)
        with t_whatif:
            _render_whatif(holdings_raw)

    # ── Planning Workspace (isolated — does not touch any existing logic) ──
    _render_planning_workspace(holdings_raw, totals, df_long)

    # ── Stage 4: Before vs After comparison layer ─────────────────────────
    _render_before_after_section(holdings_raw, client_name)


def _filter_candidates_by_universe(df_long: "pd.DataFrame", universe: str) -> "pd.DataFrame":
    """
    Filter df_long (already-loaded product data) by target universe keyword.
    Returns the filtered dataframe; empty df if nothing matches.
    """
    if df_long is None or df_long.empty:
        return pd.DataFrame()
    _KW = {
        "קרן השתלמות":    ["השתלמות"],
        "קופת גמל":       ["גמל"],
        "קופת גמל להשקעה": ["גמל להשקעה"],
        "קרן פנסיה":      ["פנסיה"],
        "פוליסת חיסכון":  ["פוליסה", "חיסכון"],
        "ביטוח מנהלים":   ["ביטוח מנהלים"],
    }
    keywords = _KW.get(universe, [])
    if not keywords:
        return df_long.copy()   # no keyword = return all
    mask = pd.Series([False] * len(df_long), index=df_long.index)
    for col in ["fund", "track"]:
        if col in df_long.columns:
            for kw in keywords:
                mask |= df_long[col].astype(str).str.contains(kw, na=False)
    filtered = df_long[mask].copy()
    # If keyword filter finds nothing, return all (df_long may already be the right type)
    return filtered if not filtered.empty else df_long.copy()


def _build_proposed_portfolio(holdings_raw: list, actions: list) -> dict:
    """
    Build a lightweight proposed portfolio state.
    Does NOT alter holdings_raw. Returns a plain dict.
    """
    import math as _math

    # Map uid → action for quick lookup
    action_map = {a["uid"]: a for a in actions if a.get("status") == "selected"}

    total_cur = 0.0
    total_prp = 0.0
    cur_wtd   = {"equity": 0.0, "foreign": 0.0, "fx": 0.0, "illiquid": 0.0}
    prp_wtd   = {"equity": 0.0, "foreign": 0.0, "fx": 0.0, "illiquid": 0.0}
    _ALLOC_MAP = {
        "equity": "equity_pct", "foreign": "foreign_pct",
        "fx": "fx_pct", "illiquid": "illiquid_pct",
    }
    _CAND_MAP = {
        "equity": "stocks", "foreign": "foreign", "fx": "fx", "illiquid": "illiquid",
    }

    for h in holdings_raw:
        uid = h.get("uid", "")
        amt = float(h.get("amount", 0) or 0)
        total_cur += amt
        action = action_map.get(uid)

        if action:
            # Use candidate metrics for proposed side
            cand = action.get("selected_candidate", {})
            for k, ck in _CAND_MAP.items():
                v = cand.get(ck)
                if v is not None:
                    try:
                        fv = float(v)
                        if not _math.isnan(fv):
                            prp_wtd[k] += fv * amt
                    except (TypeError, ValueError):
                        pass
            total_prp += amt
        else:
            # Frozen — same on both sides
            for k, hk in _ALLOC_MAP.items():
                v = h.get(hk)
                if v is not None:
                    try:
                        fv = float(v)
                        if not _math.isnan(fv):
                            prp_wtd[k] += fv * amt
                    except (TypeError, ValueError):
                        pass
            total_prp += amt

        # Current side always from holdings
        for k, hk in _ALLOC_MAP.items():
            v = h.get(hk)
            if v is not None:
                try:
                    fv = float(v)
                    if not _math.isnan(fv):
                        cur_wtd[k] += fv * amt
                except (TypeError, ValueError):
                    pass

    def _div(d, total):
        return {k: round(v / total, 2) if total > 0 else float("nan")
                for k, v in d.items()}

    return {
        "current_totals":  _div(cur_wtd, total_cur),
        "proposed_totals": _div(prp_wtd, total_prp),
        "n_replaced":      len(action_map),
        "total_value":     total_cur,
    }


def _render_planning_workspace(holdings_raw: list, totals: dict,
                               df_long: "pd.DataFrame | None" = None) -> None:
    """
    Isolated planning workspace — stages 1 + 2.
    Reads holdings_raw and df_long as read-only.
    Writes only to: planning_actions, planning_proposed_portfolio.
    """
    st.markdown("---")
    with st.expander("🗂️ תכנון שינוי תיק", expanded=False):

        if not holdings_raw:
            st.info("אין אחזקות לתכנון. הוסף מוצרים בשלב 1.")
            return

        # ── Current portfolio summary ─────────────────────────────────────
        st.markdown("##### 📊 תמהיל נוכחי משוקלל")
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("מניות",    _fmt(totals.get("equity")))
        s2.metric('חו"ל',     _fmt(totals.get("foreign")))
        s3.metric('מט"ח',     _fmt(totals.get("fx")))
        s4.metric("לא סחיר",  _fmt(totals.get("illiquid")))

        st.markdown("---")
        st.markdown("##### 📋 בחר אחזקות לשינוי")

        _UNIVERSES = [
            "ללא שינוי",
            "קרן השתלמות",
            "קופת גמל",
            "קופת גמל להשקעה",
            "קרן פנסיה",
            "פוליסת חיסכון",
            "ביטוח מנהלים",
        ]

        existing_actions = st.session_state.get("planning_actions", [])
        existing_uids_map = {a["uid"]: a for a in existing_actions}

        for h in holdings_raw:
            uid      = h.get("uid", "")
            name     = h.get("product_name", "")
            provider = h.get("provider", "")
            amount   = h.get("amount", 0.0)
            ptype    = h.get("product_type", "")

            _dd_key = f"plan_uni_{uid}"

            # Determine current selection from session state or existing actions
            current_universe = existing_uids_map.get(uid, {}).get("target_universe", "ללא שינוי")
            current_idx = _UNIVERSES.index(current_universe) if current_universe in _UNIVERSES else 0

            col_name, col_mgr, col_amt, col_dd = st.columns([3, 2, 1.5, 2])
            with col_name:
                st.caption(name or "—")
            with col_mgr:
                st.caption(provider or "—")
            with col_amt:
                st.caption(_ils(float(amount)) if amount else "—")
            with col_dd:
                universe = st.selectbox(
                    "יקום", options=_UNIVERSES, index=current_idx,
                    key=_dd_key, label_visibility="collapsed",
                )

            # Auto-add/update planning actions on any selection change
            if universe != "ללא שינוי":
                action_entry = {
                    "uid": uid, "original_product": name,
                    "manager": provider, "amount": float(amount) if amount else 0.0,
                    "current_type": ptype, "target_universe": universe,
                    "status": existing_uids_map.get(uid, {}).get("status", "pending"),
                }
                if uid not in existing_uids_map:
                    existing_actions.append(action_entry)
                    existing_uids_map[uid] = action_entry
                    st.session_state["planning_actions"] = existing_actions
                elif existing_uids_map[uid].get("target_universe") != universe:
                    for act in existing_actions:
                        if act["uid"] == uid:
                            act["target_universe"] = universe
                    st.session_state["planning_actions"] = existing_actions
            else:
                # If switched back to "ללא שינוי", remove from queue
                if uid in existing_uids_map:
                    st.session_state["planning_actions"] = [
                        a for a in existing_actions if a["uid"] != uid
                    ]
                    existing_actions = st.session_state["planning_actions"]
                    existing_uids_map = {a["uid"]: a for a in existing_actions}

        st.markdown("---")

        # ── Planning queue + per-action candidate selection ───────────────
        _queue = st.session_state.get("planning_actions", [])
        if _queue:
            st.markdown("##### 📥 תור תכנון")

            # Summary table
            _q_rows = []
            for a in _queue:
                cand = a.get("selected_candidate", {})
                _q_rows.append({
                    "מוצר מקורי":     a.get("original_product", "—"),
                    "מנהל":           a.get("manager", "—"),
                    "סכום":           _ils(a.get("amount", 0)),
                    "יקום יעד":       a.get("target_universe", "—"),
                    "חלופה נבחרת":    cand.get("fund", "—") if cand else "—",
                    "סטטוס":          a.get("status", "—"),
                })
            st.dataframe(pd.DataFrame(_q_rows), use_container_width=True, hide_index=True)

            # Per-action candidate selection panels
            for ai, action in enumerate(_queue):
                uid     = action.get("uid", "")
                uni     = action.get("target_universe", "ללא שינוי")
                orig    = action.get("original_product", "")
                cur_mgr = action.get("manager", "")
                status  = action.get("status", "pending")

                col_lbl, col_btn = st.columns([4, 1])
                with col_lbl:
                    st.markdown(
                        f"**{orig}** → `{uni}` "
                        f"{'✅ נבחרה חלופה' if status == 'selected' else ''}"
                    )
                with col_btn:
                    if st.button("🔍 בחר חלופה", key=f"plan_open_btn_{uid}"):
                        # toggle
                        cur = st.session_state.get(f"plan_open_{uid}", False)
                        st.session_state[f"plan_open_{uid}"] = not cur
                        st.rerun()

                if st.session_state.get(f"plan_open_{uid}", False):
                    with st.container():
                        if uni == "ללא שינוי":
                            st.info("הגדר יקום יעד שונה מ'ללא שינוי' כדי לחפש חלופות.")
                        elif df_long is None or df_long.empty:
                            st.warning("אין נתוני מוצרים זמינים לחיפוש חלופות.")
                        else:
                            candidates = _filter_candidates_by_universe(df_long, uni)
                            all_mgrs = sorted(candidates["manager"].dropna().unique().tolist()) \
                                if not candidates.empty else []

                            fc1, fc2 = st.columns([3, 1])
                            with fc1:
                                sel_mgrs = st.multiselect(
                                    "סינון לפי מנהל", options=all_mgrs,
                                    default=all_mgrs, key=f"plan_mgr_{uid}",
                                )
                            with fc2:
                                max_cands = st.number_input(
                                    "מקסימום", min_value=1, max_value=50,
                                    value=10, step=1, key=f"plan_max_{uid}",
                                )

                            filtered = candidates.copy()
                            if sel_mgrs:
                                filtered = filtered[filtered["manager"].isin(sel_mgrs)]
                            if "service" in filtered.columns:
                                filtered = filtered.sort_values(
                                    "service", ascending=False, na_position="last"
                                )
                            elif "sharpe" in filtered.columns:
                                filtered = filtered.sort_values(
                                    "sharpe", ascending=False, na_position="last"
                                )
                            filtered = filtered.head(int(max_cands)).reset_index(drop=True)

                            if filtered.empty:
                                st.info("לא נמצאו חלופות מתאימות עם הסינון הנוכחי.")
                            else:
                                # ── Build display table ───────────────────────
                                disp_cols = [c for c in ["manager", "fund", "track"]
                                             if c in filtered.columns]
                                num_cols  = [c for c in ["service", "sharpe", "stocks",
                                                          "foreign", "fx", "illiquid"]
                                             if c in filtered.columns]
                                _COL_HEB = {
                                    "manager": "מנהל", "fund": "מוצר", "track": "מסלול",
                                    "sharpe": "שארפ", "service": "שירות",
                                    "stocks": "מניות %", "foreign": 'חו"ל %',
                                    "fx": 'מט"ח %', "illiquid": "לא סחיר %",
                                }
                                # Render each candidate as a clickable row
                                for ci in range(len(filtered)):
                                    row = filtered.iloc[ci]
                                    mgr_name  = str(row.get("manager", "—"))
                                    fund_name = str(row.get("fund", "—"))
                                    track_name = str(row.get("track", "—"))
                                    service_val = row.get("service")
                                    sharpe_val  = row.get("sharpe")

                                    is_selected = (
                                        (action.get("selected_candidate") or {}).get("fund") == fund_name
                                        and action.get("status") == "selected"
                                    )
                                    highlight = "background:#EFF6FF;border:1.5px solid #3A7AFE;" if is_selected else "background:#F9FAFB;border:1px solid #E5E7EB;"
                                    badge = " ✅" if is_selected else ""

                                    stats_parts = []
                                    if service_val is not None:
                                        try: stats_parts.append(f"שירות: {float(service_val):.1f}%")
                                        except: pass
                                    if sharpe_val is not None:
                                        try: stats_parts.append(f"שארפ: {float(sharpe_val):.2f}")
                                        except: pass
                                    for col_k, col_lbl in [("stocks","מניות"),("foreign",'חו"ל'),("fx",'מט"ח'),("illiquid","לא סחיר")]:
                                        v = row.get(col_k)
                                        if v is not None:
                                            try: stats_parts.append(f"{col_lbl}: {float(v):.1f}%")
                                            except: pass
                                    stats_str = " | ".join(stats_parts)

                                    btn_col, info_col = st.columns([1.8, 5])
                                    with btn_col:
                                        if st.button(
                                            f"{'✅ נבחר' if is_selected else '▶ בחר'}",
                                            key=f"plan_pick_{uid}_{ci}",
                                            type="primary" if is_selected else "secondary",
                                            use_container_width=True,
                                        ):
                                            chosen = row.to_dict()
                                            cross_mgr = (str(chosen.get("manager", "")) != cur_mgr)
                                            for act in st.session_state["planning_actions"]:
                                                if act["uid"] == uid:
                                                    act["status"] = "selected"
                                                    act["selected_candidate"] = {
                                                        "fund":    str(chosen.get("fund", "")),
                                                        "manager": str(chosen.get("manager", "")),
                                                        "track":   str(chosen.get("track", "")),
                                                        "sharpe":  chosen.get("sharpe"),
                                                        "service": chosen.get("service"),
                                                        "cross_manager": bool(cross_mgr),
                                                    }
                                                    break
                                            st.session_state["planning_proposed_portfolio"] = \
                                                _build_proposed_portfolio(
                                                    holdings_raw,
                                                    st.session_state["planning_actions"],
                                                )
                                            st.session_state[f"plan_open_{uid}"] = False
                                            st.rerun()
                                    with info_col:
                                        st.markdown(
                                            f"<div style='{highlight}border-radius:6px;padding:5px 10px;direction:rtl'>"
                                            f"<b>{mgr_name}</b> | {fund_name} | <span style='color:#6B7280'>{track_name}</span>{badge}"
                                            f"<br><span style='font-size:11px;color:#64748b'>{stats_str}</span>"
                                            f"</div>",
                                            unsafe_allow_html=True,
                                        )
                st.markdown("---")
            if st.button("🗑️ נקה תור", key="plan_clear_btn", type="secondary"):
                st.session_state["planning_actions"] = []
                st.session_state["planning_proposed_portfolio"] = None
                st.rerun()

        # ── Stage 3: Comparison + report layer ───────────────────────────
        _proposed = st.session_state.get("planning_proposed_portfolio")
        _queue    = st.session_state.get("planning_actions", [])  # refresh
        _selected_actions = [a for a in _queue if a.get("status") == "selected"]

        if _selected_actions or _proposed:
            st.markdown("##### 🔄 מצב מוצע ראשוני")
            mp1, mp2 = st.columns(2)
            mp1.metric("מוצרים שהוחלפו", len(_selected_actions))
            mp2.metric("פעולות ממתינות",
                       len([a for a in _queue if a.get("status") == "pending"]))

            # ── Comparison table (action-level) ───────────────────────────────
            comp_rows = []
            for a in _queue:
                cand    = a.get("selected_candidate") or {}
                orig_mgr = a.get("manager", "")
                new_mgr  = cand.get("manager", "—")
                comp_rows.append({
                    "מוצר מקורי":  a.get("original_product", "—"),
                    "יקום יעד":    a.get("target_universe", "—"),
                    "חלופה נבחרת": cand.get("fund", "—"),
                    "מנהל חדש":    new_mgr,
                    "שינוי מנהל":  "כן" if (cand and new_mgr != orig_mgr) else "לא",
                    "סטטוס":       a.get("status", "—"),
                })
            st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)

            # ── Weighted allocation side-by-side ──────────────────────────────
            if _proposed:
                import math as _math
                _cur = _proposed.get("current_totals") or {}
                _prp = _proposed.get("proposed_totals") or {}
                if _cur and _prp:
                    st.markdown("**השוואת תמהיל: נוכחי → מוצע**")
                    cc1, cc2, cc3, cc4 = st.columns(4)
                    for _col, _key, _lbl in [
                        (cc1, "equity",   "מניות %"),
                        (cc2, "foreign",  'חו"ל %'),
                        (cc3, "fx",       'מט"ח %'),
                        (cc4, "illiquid", "לא סחיר %"),
                    ]:
                        _cv = _cur.get(_key)
                        _pv = _prp.get(_key)
                        _ok = (_cv is not None and _pv is not None
                               and not _math.isnan(float(_cv))
                               and not _math.isnan(float(_pv)))
                        if _ok:
                            _delta = float(_pv) - float(_cv)
                            _col.metric(
                                _lbl,
                                f"{float(_pv):.1f}%",
                                delta=f"{_delta:+.1f}pp",
                            )
                        else:
                            _col.metric(_lbl, "N/A")
                else:
                    st.caption("⚠️ תמהיל מוצע חלקי — חסרים נתוני חשיפה בחלופות שנבחרו.")

            # ── Report download ───────────────────────────────────────────────
            try:
                from reporting.report_models import PortfolioSnapshot
                from reporting.report_builder import (
                    build_portfolio_comparison,
                    build_optimizer_html,
                    build_isa_html,
                )
                from reporting.report_models import OptimizerReportInput, OptimizerAlternative

                _tot_val = float((_proposed or {}).get("total_value") or 1.0)
                _cur_t   = (_proposed or {}).get("current_totals") or {}
                _prp_t   = (_proposed or {}).get("proposed_totals") or {}

                _snap_cur = PortfolioSnapshot(
                    total_value    = _tot_val,
                    allocations    = {
                        "equities": float(_cur_t.get("equity")  or float("nan")),
                        "abroad":   float(_cur_t.get("foreign") or float("nan")),
                        "fx":       float(_cur_t.get("fx")      or float("nan")),
                        "illiquid": float(_cur_t.get("illiquid")or float("nan")),
                    },
                )
                _snap_prp = PortfolioSnapshot(
                    total_value    = _tot_val,
                    allocations    = {
                        "equities": float(_prp_t.get("equity")  or float("nan")),
                        "abroad":   float(_prp_t.get("foreign") or float("nan")),
                        "fx":       float(_prp_t.get("fx")      or float("nan")),
                        "illiquid": float(_prp_t.get("illiquid")or float("nan")),
                    },
                )
                _cmp = build_portfolio_comparison(_snap_cur, _snap_prp)

                # Build optimizer alternatives from selected actions
                _alts = []
                for _a in _selected_actions:
                    _c = _a.get("selected_candidate") or {}
                    _alts.append(OptimizerAlternative(
                        label        = _a.get("original_product", ""),
                        managers     = _c.get("manager", ""),
                        funds        = _c.get("fund", ""),
                        tracks       = _c.get("track", ""),
                        weights      = (),
                        sharpe       = float(_c["sharpe"]) if _c.get("sharpe") is not None else float("nan"),
                        service      = float(_c["service"]) if _c.get("service") is not None else float("nan"),
                        advantage    = _a.get("target_universe", ""),
                    ))

                if _alts:
                    _rpt_input = OptimizerReportInput(
                        alternatives = _alts,
                        targets      = {},
                        product_type = "תכנון שינוי תיק",
                    )
                    _html = build_optimizer_html(_rpt_input)
                    st.download_button(
                        "⬇️ הורד דוח תכנון (HTML)",
                        data=_html.encode("utf-8"),
                        file_name="planning_report.html",
                        mime="text/html",
                        key="plan_dl_report",
                    )
            except Exception as _rpt_e:
                st.caption(f"⚠️ לא ניתן להפיק דוח: {_rpt_e}")

        # ── Debug expander ────────────────────────────────────────────────
        with st.expander("🔍 מידע אבחון — תכנון", expanded=False):
            _missing = [h.get("product_name","—") for h in holdings_raw
                        if not h.get("amount") or not h.get("provider")]
            _cands_src = "df_long (טאב פעיל)" if (df_long is not None and not df_long.empty) else "לא זמין"
            _n_cands   = len(df_long) if (df_long is not None and not df_long.empty) else 0
            _proposed_ok = _proposed is not None
            st.caption(
                f"**מקור חלופות:** {_cands_src}  \n"
                f"**מספר מוצרים במאגר:** {_n_cands}  \n"
                f"**פעולות בתור:** {len(_queue)}  \n"
                f"**פעולות שנבחרו:** {len(_selected_actions)}  \n"
                f"**תיק מוצע נבנה:** {'✅' if _proposed_ok else '⚠️ טרם נבנה'}  \n"
                f"**מוצרים עם נתונים חסרים:** "
                + (", ".join(_missing) if _missing else "אין")
            )


def _safe_f(v) -> float:
    import math
    try:
        f = float(v)
        return f if not math.isnan(f) else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _snap_from_holdings(holdings_raw: list) -> dict:
    import math
    if not holdings_raw:
        return {}
    total = sum(_safe_f(h.get("amount", 0)) for h in holdings_raw)
    if total <= 0:
        return {}
    def _wt(col):
        valid = [(h, _safe_f(h.get("amount", 0))) for h in holdings_raw
                 if not math.isnan(_safe_f(h.get(col))) and _safe_f(h.get("amount", 0)) > 0]
        if not valid:
            return float("nan")
        vt = sum(a for _, a in valid)
        return sum(_safe_f(h.get(col)) * a for h, a in valid) / vt if vt > 0 else float("nan")
    return {
        "total": total, "equity": _wt("equity_pct"), "foreign": _wt("foreign_pct"),
        "fx": _wt("fx_pct"), "illiquid": _wt("illiquid_pct"), "sharpe": _wt("sharpe"),
        "service": _wt("service"), "cost": _wt("annual_cost_pct"),
        "n_products": len(holdings_raw),
        "n_managers": len({h.get("provider","") for h in holdings_raw}),
    }


def _snap_from_proposed(holdings_raw: list, actions: list) -> dict:
    uid_map = {a["uid"]: a for a in actions if a.get("status") == "selected"}
    proposed = []
    for h in holdings_raw:
        action = uid_map.get(h.get("uid", ""))
        if action:
            c = action.get("selected_candidate") or {}
            proposed.append({
                **h,
                "equity_pct":   _safe_f(c.get("stocks")),
                "foreign_pct":  _safe_f(c.get("foreign")),
                "fx_pct":       _safe_f(c.get("fx")),
                "illiquid_pct": _safe_f(c.get("illiquid")),
                "sharpe":       _safe_f(c.get("sharpe")),
                "service":      _safe_f(c.get("service")),
                "provider":     c.get("manager", h.get("provider", "")),
                "product_name": c.get("fund",    h.get("product_name", "")),
            })
        else:
            proposed.append(h)
    return _snap_from_holdings(proposed)


def _build_comparison_html(cur: dict, prp: dict, actions: list, client_name: str = "") -> str:
    import math, html as _he
    from datetime import date as _date
    def _pct(v):
        try:
            f = float(v); return f"{f:.1f}%" if not math.isnan(f) else "N/A"
        except: return "N/A"
    def _dlt(c, p):
        try:
            fc, fp = float(c), float(p)
            if math.isnan(fc) or math.isnan(fp): return "N/A"
            d = fp - fc; s = "+" if d >= 0 else ""; return f"{s}{d:.1f}pp"
        except: return "N/A"
    METRICS = [("מניות %","equity"),('חו"ל %',"foreign"),('מט"ח %',"fx"),
               ("לא סחיר %","illiquid"),("שארפ","sharpe"),("שירות","service"),("עלות %","cost")]
    rows = "".join(
        f"<tr><td>{lbl}</td><td>{_pct(cur.get(k))}</td>"
        f"<td>{_pct(prp.get(k))}</td><td>{_dlt(cur.get(k),prp.get(k))}</td></tr>"
        for lbl, k in METRICS
    )
    act_lines = ""
    for a in actions:
        c = a.get("selected_candidate") or {}
        orig = _he.escape(a.get("original_product","—"))
        new  = _he.escape(c.get("fund","—"))
        mgr_note = "נשמר אותו גוף" if a.get("manager") == c.get("manager") else "מעבר בין גופים"
        if a.get("status") == "selected":
            act_lines += f"<li>הוחלף <b>{orig}</b> בחלופה <b>{new}</b> — {mgr_note}</li>"
        else:
            act_lines += f"<li>ממתין: <b>{orig}</b></li>"
    pending = sum(1 for a in actions if a.get("status") != "selected")
    partial = (f"<p style='color:#b45309;background:#fef3c7;padding:7px 12px;"
               f"border-radius:6px;font-size:12px'>⚠️ {pending} פעולות ממתינות</p>") if pending else ""
    title = _he.escape(client_name) if client_name else "לקוח"
    today = _date.today().strftime("%d/%m/%Y")
    return f"""<!DOCTYPE html>
<html dir="rtl" lang="he"><head><meta charset="utf-8"/>
<title>דוח תכנון — {title}</title>
<style>
body{{font-family:'Segoe UI',Arial,sans-serif;direction:rtl;background:#f5f7fa;padding:22px}}
.hdr{{background:#1F3A5F;color:#fff;border-radius:10px;padding:16px 22px;margin-bottom:18px}}
.hdr h1{{margin:0;font-size:19px}}.hdr .sub{{font-size:11px;color:#93b4e0;margin-top:3px}}
.sec{{background:#fff;border:1px solid #e5eaf2;border-radius:10px;padding:14px 18px;margin-bottom:14px}}
.sec h2{{font-size:13px;color:#1F3A5F;margin:0 0 10px;border-bottom:2px solid #EFF6FF;padding-bottom:5px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:#1F3A5F;color:#fff;padding:6px 10px;text-align:right}}
td{{padding:5px 10px;border-bottom:1px solid #f1f5f9;text-align:right}}
tr:nth-child(even) td{{background:#f9fafb}}
ul{{margin:4px 0;padding-right:16px;font-size:12px;line-height:1.7}}
.footer{{font-size:10px;color:#9CA3AF;text-align:center;margin-top:20px}}
</style></head><body>
<div class="hdr"><h1>📊 דוח תכנון שינוי תיק — {title}</h1>
<div class="sub">{today} | מסמך ראשוני לצורכי תכנון בלבד</div></div>
{partial}
<div class="sec"><h2>📊 השוואה: נוכחי ← → מוצע</h2>
<table><thead><tr><th>מדד</th><th>נוכחי</th><th>מוצע</th><th>שינוי</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<div class="sec"><h2>🔄 סיכום פעולות</h2><ul>{act_lines}</ul></div>
<div class="footer">הופק אוטומטית · {today}</div>
</body></html>"""


def _render_before_after_section(holdings_raw: list, client_name: str = "") -> None:
    """Stage 4: Before vs After comparison. Reads planning_actions only."""
    import math as _m
    actions  = st.session_state.get("planning_actions", [])
    selected = [a for a in actions if a.get("status") == "selected"]
    if not selected:
        return

    st.markdown("---")
    st.markdown("""
<div style='background:linear-gradient(135deg,#1F3A5F 0%,#2563eb 100%);
     border-radius:12px;padding:14px 20px;margin-bottom:14px;direction:rtl'>
  <div style='color:#fff;font-size:16px;font-weight:900'>🔄 השוואת מצב נוכחי מול הצעה</div>
  <div style='color:#93c5fd;font-size:11px;margin-top:2px'>תמהיל נוכחי ← → תמהיל מוצע</div>
</div>""", unsafe_allow_html=True)

    cur_snap = _snap_from_holdings(holdings_raw)
    prp_snap = _snap_from_proposed(holdings_raw, actions)

    pending = len([a for a in actions if a.get("status") != "selected"])
    if pending:
        st.info(f"⚠️ ההשוואה מבוססת על {len(selected)} פעולות שנבחרו — {pending} ממתינות.")

    METRICS = [("מניות %","equity"),('חו"ל %',"foreign"),('מט"ח %',"fx"),
               ("לא סחיר %","illiquid"),("שארפ","sharpe"),("שירות","service"),("עלות %","cost")]
    cols = st.columns(len(METRICS))
    for col, (lbl, key) in zip(cols, METRICS):
        cv, pv = cur_snap.get(key), prp_snap.get(key)
        try:
            fc, fp = float(cv or "nan"), float(pv or "nan")
            prop_str = f"{fp:.1f}%" if not _m.isnan(fp) else "N/A"
            delta    = f"{fp-fc:+.1f}pp" if not (_m.isnan(fc) or _m.isnan(fp)) else None
            cur_str  = f"{fc:.1f}%"    if not _m.isnan(fc) else "N/A"
        except (TypeError, ValueError):
            prop_str, delta, cur_str = "N/A", None, "N/A"
        col.metric(lbl, prop_str, delta=delta, help=f"נוכחי: {cur_str}")

    st.markdown("##### 📊 טבלת השוואה")
    tbl = []
    for lbl, key in METRICS:
        cv, pv = cur_snap.get(key), prp_snap.get(key)
        try:
            fc, fp = float(cv or "nan"), float(pv or "nan")
            cur_str  = f"{fc:.1f}%" if not _m.isnan(fc) else "N/A"
            prop_str = f"{fp:.1f}%" if not _m.isnan(fp) else "N/A"
            if not (_m.isnan(fc) or _m.isnan(fp)):
                diff = fp - fc
                sign = "+" if diff >= 0 else ""
                color = "#16a34a" if diff >= 0 else "#dc2626"
                delta_str = f"<span style='color:{color};font-weight:700'>{sign}{diff:.1f}pp</span>"
            else:
                delta_str = "N/A"
            tbl.append((lbl, cur_str, prop_str, delta_str))
        except (TypeError, ValueError):
            tbl.append((lbl, "N/A", "N/A", "N/A"))

    rows_html = "".join(
        f"<tr><td style='font-weight:700;color:#1F3A5F'>{r[0]}</td>"
        f"<td>{r[1]}</td><td>{r[2]}</td><td>{r[3]}</td></tr>"
        for r in tbl
    )
    st.markdown(f"""
<div style='overflow-x:auto;direction:rtl'>
<table style='width:100%;border-collapse:collapse;font-size:13px;direction:rtl'>
<thead><tr style='background:#1F3A5F;color:#fff'>
  <th style='padding:8px 12px;text-align:right'>מדד</th>
  <th style='padding:8px 12px;text-align:right'>נוכחי</th>
  <th style='padding:8px 12px;text-align:right'>מוצע</th>
  <th style='padding:8px 12px;text-align:right'>שינוי</th>
</tr></thead>
<tbody style=''>
{"".join(f"<tr style='border-bottom:1px solid #E5E7EB;background:{'#F9FAFB' if i%2==0 else '#fff'}'>"
         f"<td style='padding:7px 12px;font-weight:700;color:#1F3A5F'>{r[0]}</td>"
         f"<td style='padding:7px 12px'>{r[1]}</td>"
         f"<td style='padding:7px 12px'>{r[2]}</td>"
         f"<td style='padding:7px 12px'>{r[3]}</td></tr>"
         for i, r in enumerate(tbl))}
</tbody>
</table>
</div>""", unsafe_allow_html=True)

    st.markdown("##### 📋 פעולות תכנון")
    act_tbl = []
    for a in actions:
        c = a.get("selected_candidate") or {}
        act_tbl.append({"מוצר מקורי": a.get("original_product","—"),
                         "יקום יעד": a.get("target_universe","—"),
                         "חלופה נבחרת": c.get("fund","—"),
                         "שינוי מנהל": "כן" if (c and c.get("manager") and c.get("manager") != a.get("manager")) else "לא",
                         "סטטוס": a.get("status","—")})
    st.dataframe(pd.DataFrame(act_tbl), use_container_width=True, hide_index=True)

    st.markdown("##### 📝 סיכום פעולות שבוצעו")
    for a in selected:
        c = a.get("selected_candidate") or {}
        mgr_note = "נשמר אותו גוף" if a.get("manager") == c.get("manager") else "מעבר בין גופים"
        st.markdown(f"✅ הוחלף **{a.get('original_product','—')}** בחלופה **{c.get('fund','—')}** — _{mgr_note}_")
    for a in [x for x in actions if x.get("status") != "selected"]:
        st.markdown(f"⏳ ממתין: **{a.get('original_product','—')}**")

    st.markdown("---")
    if st.button("📄 תצוגת דוח מסכם", key="plan_show_report_btn"):
        st.session_state["plan_show_report"] = not st.session_state.get("plan_show_report", False)

    if st.session_state.get("plan_show_report", False):
        html_report = _build_comparison_html(cur_snap, prp_snap, actions, client_name)
        import streamlit.components.v1 as _stc
        _stc.html(html_report, height=600, scrolling=True)
        st.download_button("⬇️ הורד דוח (HTML)", data=html_report.encode("utf-8"),
                           file_name="planning_comparison.html", mime="text/html",
                           key="plan_dl_html")

    with st.expander("🔍 אבחון — השוואת תיקים", expanded=False):
        avail   = [lbl for lbl, key in METRICS if not _m.isnan(float(cur_snap.get(key) or "nan"))]
        missing = [lbl for lbl, key in METRICS if lbl not in avail]
        st.caption(
            f"**פעולות שנבחרו:** {len(selected)}  \n"
            f"**תמונה נוכחית:** {'✅' if cur_snap else '❌'}  \n"
            f"**תמונה מוצעת:** {'✅' if prp_snap else '❌'}  \n"
            f"**מדדים זמינים:** {', '.join(avail) if avail else 'אין'}  \n"
            f"**מדדים חסרים:** {', '.join(missing) if missing else 'אין'}"
        )



def _render_downloads_page(df, totals, client_name, holdings_raw):
    """Enhanced export tab with NotebookLM package."""
    import streamlit as st
    from client_portfolio.report_builder import (
        build_html_report, build_notebook, build_notebooklm_package
    )

    holdings = _enrich_costs(holdings_raw)
    df_full = pd.DataFrame(holdings)
    for col in ["amount","equity_pct","foreign_pct","fx_pct","illiquid_pct","sharpe","annual_cost_pct"]:
        if col in df_full.columns:
            df_full[col] = pd.to_numeric(df_full[col], errors="coerce")
    if "excluded" not in df_full.columns:
        df_full["excluded"] = False

    from client_portfolio.charts import compute_totals
    totals_full = compute_totals(df_full)

    html_bytes = build_html_report(df_full, client_name, totals_full)
    nb_bytes   = build_notebook(df_full, client_name, totals_full)
    nlm_bytes  = build_notebooklm_package(df_full, client_name, totals_full)
    csv_bytes  = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

    # ── Download buttons grid ─────────────────────────────────────────────
    dc1, dc2, dc3, dc4 = st.columns(4)
    with dc1:
        st.markdown("""
<div style='background:#F0F4FF;border-radius:10px;padding:14px 16px 10px 16px;
     text-align:center;direction:rtl;margin-bottom:8px'>
  <div style='font-size:22px;margin-bottom:4px'>📄</div>
  <div style='font-size:14px;font-weight:800;color:#1F3A5F'>דוח HTML</div>
  <div style='font-size:11px;color:#64748b;margin-top:3px'>מעוצב · מוכן להדפסה</div>
</div>""", unsafe_allow_html=True)
        st.download_button("📄 הורד דוח", data=html_bytes,
                           file_name=f"portfolio_{client_name or 'client'}.html",
                           mime="text/html", key="cppage_dl_html",
                           use_container_width=True, type="primary")
    with dc2:
        st.markdown("""
<div style='background:#F0F4FF;border-radius:10px;padding:14px 16px 10px 16px;
     text-align:center;direction:rtl;margin-bottom:8px'>
  <div style='font-size:22px;margin-bottom:4px'>📓</div>
  <div style='font-size:14px;font-weight:800;color:#1F3A5F'>Jupyter Notebook</div>
  <div style='font-size:11px;color:#64748b;margin-top:3px'>Run All ב-Colab → גרפים</div>
</div>""", unsafe_allow_html=True)
        st.download_button("📓 הורד Notebook", data=nb_bytes,
                           file_name=f"portfolio_{client_name or 'client'}.ipynb",
                           mime="application/json", key="cppage_dl_nb",
                           use_container_width=True, type="primary")
    with dc3:
        st.markdown("""
<div style='background:#F0F4FF;border-radius:10px;padding:14px 16px 10px 16px;
     text-align:center;direction:rtl;margin-bottom:8px'>
  <div style='font-size:22px;margin-bottom:4px'>🔬</div>
  <div style='font-size:14px;font-weight:800;color:#1F3A5F'>NotebookLM Package</div>
  <div style='font-size:11px;color:#64748b;margin-top:3px'>נתונים + פרומפט מצגת</div>
</div>""", unsafe_allow_html=True)
        st.download_button("🔬 הורד Package", data=nlm_bytes,
                           file_name=f"notebooklm_{client_name or 'client'}.md",
                           mime="text/markdown", key="cppage_dl_nlm",
                           use_container_width=True, type="primary")
    with dc4:
        st.markdown("""
<div style='background:#F0F4FF;border-radius:10px;padding:14px 16px 10px 16px;
     text-align:center;direction:rtl;margin-bottom:8px'>
  <div style='font-size:22px;margin-bottom:4px'>⬇️</div>
  <div style='font-size:14px;font-weight:800;color:#1F3A5F'>נתונים גולמיים</div>
  <div style='font-size:11px;color:#64748b;margin-top:3px'>CSV לעיבוד עצמאי</div>
</div>""", unsafe_allow_html=True)
        st.download_button("⬇️ הורד CSV", data=csv_bytes,
                           file_name="portfolio.csv", mime="text/csv",
                           key="cppage_dl_csv", use_container_width=True)

    st.markdown("---")

    # ── Usage instructions — two clean columns ────────────────────────────
    col_nlm, col_jup = st.columns(2)

    with col_nlm:
        st.markdown("""
<div style='background:#F8FAFF;border:1px solid #CBD5E1;border-radius:10px;
     padding:16px 18px;direction:rtl'>
  <div style='font-size:14px;font-weight:800;color:#1F3A5F;margin-bottom:10px'>
    🔬 NotebookLM — איך להשתמש
  </div>
  <ol style='margin:0;padding-right:18px;color:#374151;font-size:13px;line-height:2'>
    <li>הורד קובץ <strong>NotebookLM Package</strong> <code>(.md)</code></li>
    <li>פתח <a href="https://notebooklm.google.com" target="_blank">NotebookLM</a></li>
    <li><code>Add source</code> ← <code>Upload</code> ← בחר את הקובץ</li>
    <li>NotebookLM ינתח את התיק ויענה על כל שאלה</li>
  </ol>
</div>""", unsafe_allow_html=True)

    with col_jup:
        st.markdown("""
<div style='background:#F8FAFF;border:1px solid #CBD5E1;border-radius:10px;
     padding:16px 18px;direction:rtl'>
  <div style='font-size:14px;font-weight:800;color:#1F3A5F;margin-bottom:10px'>
    📓 Jupyter / Colab — איך להשתמש
  </div>
  <ol style='margin:0;padding-right:18px;color:#374151;font-size:13px;line-height:2'>
    <li>הורד <strong>Jupyter Notebook</strong> <code>(.ipynb)</code></li>
    <li>פתח <a href="https://colab.research.google.com" target="_blank">Google Colab</a>
        ← <code>File → Upload notebook</code></li>
    <li><code>Runtime → Run all</code> — כל הגרפים ייוצרו אוטומטית</li>
  </ol>
</div>""", unsafe_allow_html=True)
