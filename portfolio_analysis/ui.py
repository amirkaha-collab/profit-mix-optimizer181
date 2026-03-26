# -*- coding: utf-8 -*-
"""
portfolio_analysis/ui.py
─────────────────────────
Full portfolio-analysis UI rendered as an st.expander at the app's bottom.

Entry point (one line in streamlit_app.py):
    from portfolio_analysis.ui import render_portfolio_analysis
    render_portfolio_analysis(df_long, product_type)

All session-state keys are prefixed  "pf_"  to avoid any collision.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

from portfolio_analysis.models import (
    ALLOC_COLS, ALLOC_LABELS,
    get_holdings, set_holdings, holdings_to_df,
    compute_portfolio_summary, try_autofill,
    import_from_session, make_manual_holding, build_whatif_baseline,
)

# ── Constants ─────────────────────────────────────────────────────────────────

from portfolio_analysis.catalog import (
    ALL_PRODUCT_TYPES, SUPPORTED_CATALOG_TYPES, MANUAL_ONLY_TYPES,
    normalize_product_type, is_catalog_supported, get_product_entry_mode,
    get_catalog_managers, get_catalog_funds, get_catalog_tracks, get_catalog_preview,
)
PRODUCT_TYPES = ALL_PRODUCT_TYPES

_SRC_BADGE = {
    "imported":          ("🔵", "יובא"),
    "manual":            ("✏️", "ידני"),
    "auto_filled":       ("🟢", "מולא אוטו׳"),
    "missing":           ("🔴", "חסר"),
}

# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
<style>
.pf-table { width:100%; border-collapse:collapse; font-size:13px; direction:rtl; }
.pf-table th {
  background:#1F3A5F; color:#fff; padding:7px 10px;
  text-align:right; font-weight:700; white-space:nowrap;
}
.pf-table td { padding:6px 10px; border-bottom:1px solid #E5E7EB; vertical-align:middle; }
.pf-table tr:hover td { background:#F0F4FF; }
.pf-table tr.summary-row td {
  background:#EFF6FF; font-weight:800; border-top:2px solid #3A7AFE;
}
.pf-table tr.excluded td { opacity:0.45; text-decoration:line-through; }
.pf-badge { display:inline-block; border-radius:4px; padding:2px 7px;
            font-size:11px; font-weight:700; }
.pf-badge-missing  { background:#FEE2E2; color:#B91C1C; }
.pf-badge-imported { background:#DBEAFE; color:#1D4ED8; }
.pf-badge-manual   { background:#FEF3C7; color:#92400E; }
.pf-badge-auto     { background:#D1FAE5; color:#065F46; }
.pf-locked  { font-size:14px; cursor:default; }
</style>
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _nan_str(v, fmt="{:.1f}"):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    try:
        return fmt.format(float(v)) + "%"
    except Exception:
        return str(v)


def _fmt_amount(v: float) -> str:
    if math.isnan(v) or v == 0:
        return "—"
    if v >= 1_000_000:
        return f"₪{v/1_000_000:.2f}M"
    return f"₪{v:,.0f}"


def _source_badge(alloc_src: str) -> str:
    icon, label = _SRC_BADGE.get(alloc_src, ("❓", alloc_src))
    css_cls = {
        "imported":    "pf-badge-imported",
        "manual":      "pf-badge-manual",
        "auto_filled": "pf-badge-auto",
        "missing":     "pf-badge-missing",
    }.get(alloc_src, "pf-badge-missing")
    return f"<span class='pf-badge {css_cls}'>{icon} {label}</span>"


# ── Summary metrics row ───────────────────────────────────────────────────────

def _render_summary_metrics(summary: dict) -> None:
    if not summary:
        return
    cols = st.columns(8)
    vals = [
        ("סך נכסים",    _fmt_amount(summary.get("total_amount", 0))),
        ("מוצרים",       str(summary.get("n_total", 0))),
        ("מולאו",         str(summary.get("n_complete", 0))),
        ("חסרים",        str(summary.get("n_missing", 0))),
        ("מניות (משוקלל)", _nan_str(summary.get("equity_pct"),   "{:.1f}")),
        ('חו"ל (משוקלל)',  _nan_str(summary.get("foreign_pct"),  "{:.1f}")),
        ('מט"ח (משוקלל)',  _nan_str(summary.get("fx_pct"),       "{:.1f}")),
        ("לא סחיר",       _nan_str(summary.get("illiquid_pct"),  "{:.1f}")),
    ]
    for col, (label, value) in zip(cols, vals):
        col.metric(label, value)


# ── Portfolio HTML table ──────────────────────────────────────────────────────

def _render_portfolio_table(holdings: list[dict], df_long: pd.DataFrame) -> None:
    if not holdings:
        st.info("הפורטפוליו ריק. ייבא מסלקה או הוסף מוצר ידנית.")
        return

    # Read current tab from session state (safe – read-only, no import from streamlit_app)
    try:
        _current_tab = st.session_state.get("product_type", "")
    except Exception:
        _current_tab = ""

    # ── Inline tab-relevance logic (avoids circular import) ──
    _TAB_KEYWORDS = {
        "קרנות השתלמות": ["השתלמות"],
        "פוליסות חיסכון": ["פוליסה", "חיסכון"],
        "קרנות פנסיה":   ["פנסיה", "ביטוח מנהלים"],
        "קופות גמל":     ["גמל"],
        "גמל להשקעה":    ["להשקעה"],
    }
    def _is_tab_relevant(product_type_str: str) -> bool:
        try:
            if not _current_tab:
                return False
            kws = _TAB_KEYWORDS.get(_current_tab, [])
            pt  = str(product_type_str or "").strip()
            return any(kw in pt for kw in kws)
        except Exception:
            return False

    df = holdings_to_df(holdings)

    # ── Toggle: show only current-tab products ──
    _tab_holdings_exist = any(_is_tab_relevant(str(h.get("product_type",""))) for h in holdings)
    _show_all = True
    if _tab_holdings_exist and _current_tab:
        _show_all = not st.checkbox(
            f"הצג רק מוצרי {_current_tab}",
            value=False,
            key="pf_tab_filter_toggle",
        )

    rows_html = ""
    for _, h in df.iterrows():
        uid         = h["uid"]
        excluded    = h.get("excluded", False)
        locked      = h.get("locked", False)
        alloc_src   = h.get("allocation_source", "missing")
        row_cls     = "excluded" if excluded else ""

        _is_relevant = _is_tab_relevant(str(h.get("product_type", "")))

        # Skip non-relevant rows when filter is active
        if not _show_all and not _is_relevant:
            continue

        _row_style = "background:#EFF6FF;" if _is_relevant else ""
        _tab_dot   = (
            "<span style='color:#3A7AFE;font-size:9px;margin-left:3px' "
            "title='שייך לטאב הנוכחי'>●</span>"
            if _is_relevant else ""
        )

        lock_icon = "🔒" if locked else "🔓"
        excl_icon = "🚫" if excluded else ""

        rows_html += f"""
<tr class='{row_cls}' style='{_row_style}'>
  <td>{excl_icon} {lock_icon} <span style='font-size:10px;color:#6B7280'>{uid[:6]}</span></td>
  <td><b>{h.get('provider','')}</b></td>
  <td>{h.get('product_name','')}</td>
  <td>{h.get('track','')}</td>
  <td style='text-align:center'>
    <span style='font-size:10px;background:#F3F4F6;padding:2px 6px;border-radius:4px'>
      {_tab_dot}{h.get('product_type','')}
    </span>
  </td>
  <td style='text-align:left'>{_fmt_amount(h['amount'])}</td>
  <td style='text-align:left'>{h['weight']:.1f}%</td>
  <td style='text-align:left'>{_nan_str(h.get('equity_pct'))}</td>
  <td style='text-align:left'>{_nan_str(h.get('foreign_pct'))}</td>
  <td style='text-align:left'>{_nan_str(h.get('fx_pct'))}</td>
  <td style='text-align:left'>{_nan_str(h.get('illiquid_pct'))}</td>
  <td style='text-align:left'>{_nan_str(h.get('sharpe'), '{:.2f}').replace('%','')}</td>
  <td>{_source_badge(alloc_src)}</td>
  <td style='font-size:11px;color:#9CA3AF'>{h.get('notes','')}</td>
</tr>"""

    # Summary row — respects current filter
    df_vis_all  = df[~df["excluded"].astype(bool)] if "excluded" in df.columns else df
    if not _show_all:
        df_vis = df_vis_all[df_vis_all["product_type"].apply(
            lambda pt: _is_tab_relevant(str(pt))
        )]
    else:
        df_vis = df_vis_all
    total  = df_vis["amount"].sum()

    def _wsum(col):
        sub = df_vis[df_vis[col].notna()]
        if sub.empty:
            return "—"
        st_ = sub["amount"].sum()
        v   = (sub[col] * sub["amount"]).sum() / st_ if st_ > 0 else float("nan")
        return f"{v:.1f}%"

    rows_html += f"""
<tr class='summary-row'>
  <td colspan='5'>📊 סיכום{'  — ' + _current_tab if not _show_all and _current_tab else ''}</td>
  <td style='text-align:left'>{_fmt_amount(total)}</td>
  <td style='text-align:left'>—</td>
  <td style='text-align:left'>{_wsum('equity_pct')}</td>
  <td style='text-align:left'>{_wsum('foreign_pct')}</td>
  <td style='text-align:left'>{_wsum('fx_pct')}</td>
  <td style='text-align:left'>{_wsum('illiquid_pct')}</td>
  <td colspan='3'></td>
</tr>"""

    table_html = f"""
{_CSS}
<div style='overflow-x:auto;direction:rtl'>
<table class='pf-table'>
<thead><tr>
  <th>⚙️</th><th>גוף</th><th>מוצר</th><th>מסלול</th><th>סוג</th>
  <th>סכום</th><th>משקל</th><th>מניות</th><th>חו"ל</th><th>מט"ח</th>
  <th>לא סחיר</th><th>שארפ</th><th>מקור</th><th>הערות</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
</div>"""
    st.markdown(table_html, unsafe_allow_html=True)
    if _current_tab:
        st.caption(f"● נקודה כחולה = מוצר השייך לטאב הנוכחי ({_current_tab})")


# ── Edit controls ─────────────────────────────────────────────────────────────

def _render_edit_controls(holdings: list[dict], df_long: pd.DataFrame) -> bool:
    """
    Shows per-holding edit controls: lock, exclude, complete allocation, delete.
    Returns True if any change was made (triggers rerun).
    """
    if not holdings:
        return False

    changed = False
    st.markdown("#### 🛠️ עריכת מוצרים")

    for i, h in enumerate(holdings):
        uid        = h["uid"]
        alloc_src  = h.get("allocation_source", "missing")
        is_missing = alloc_src == "missing"
        is_excluded = h.get("excluded", False)
        is_locked   = h.get("locked", False)

        label = f"{h.get('provider','')} | {h.get('product_name','')} | {h.get('track','')}"
        with st.expander(
            f"{'🚫 ' if is_excluded else ''}{'🔒 ' if is_locked else ''}"
            f"{'🔴 ' if is_missing else ''}{label}",
            expanded=False,
        ):
            cols = st.columns([1, 1, 1, 1])
            with cols[0]:
                new_locked = st.checkbox("🔒 נעול (what-if)", value=is_locked, key=f"pf_lock_{uid}")
                if new_locked != is_locked:
                    holdings[i]["locked"] = new_locked
                    changed = True
            with cols[1]:
                new_excl = st.checkbox("🚫 החרג", value=is_excluded, key=f"pf_excl_{uid}")
                if new_excl != is_excluded:
                    holdings[i]["excluded"] = new_excl
                    changed = True
            with cols[2]:
                if st.button("🗑️ מחק", key=f"pf_del_{uid}"):
                    holdings.pop(i)
                    return True  # immediate rerun
            with cols[3]:
                # Auto-fill button
                if st.button("🔄 מלא אוטו׳", key=f"pf_auto_{uid}",
                             help="חפש נתונים מהגיליון הראשי ומלא אוטומטית"):
                    filled = try_autofill(h, df_long)
                    if filled.get("allocation_source") != alloc_src:
                        holdings[i] = filled
                        changed = True
                        st.toast("✅ מולא!")
                    else:
                        st.toast("לא נמצאו נתונים להשלמה")

            # Manual allocation completion
            if is_missing or st.session_state.get(f"pf_edit_alloc_{uid}", False):
                st.markdown("**השלם תמהיל ידנית:**")
                ac1, ac2, ac3, ac4 = st.columns(4)
                eq  = ac1.number_input("מניות %",   0.0, 100.0, float(h.get("equity_pct")   or 0), key=f"pf_eq_{uid}")
                fo  = ac2.number_input('חו"ל %',    0.0, 100.0, float(h.get("foreign_pct")  or 0), key=f"pf_fo_{uid}")
                fx  = ac3.number_input('מט"ח %',    0.0, 100.0, float(h.get("fx_pct")       or 0), key=f"pf_fx_{uid}")
                ill = ac4.number_input("לא סחיר %", 0.0, 100.0, float(h.get("illiquid_pct") or 0), key=f"pf_ill_{uid}")
                if st.button("💾 שמור תמהיל", key=f"pf_save_alloc_{uid}"):
                    holdings[i].update({
                        "equity_pct":   eq,
                        "foreign_pct":  fo,
                        "fx_pct":       fx,
                        "illiquid_pct": ill,
                        "allocation_source": "manual",
                    })
                    st.session_state[f"pf_edit_alloc_{uid}"] = False
                    changed = True
            elif alloc_src != "missing":
                if st.button("✏️ ערוך תמהיל", key=f"pf_edit_btn_{uid}"):
                    st.session_state[f"pf_edit_alloc_{uid}"] = True
                    changed = True

    if changed:
        # Persist changes to both set_holdings and CaseStore
        set_holdings(st, holdings)
        try:
            from case_management.case_store import CaseStore as _CS_ec
            _c_ec = _CS_ec.get()
            _c_ec.holdings_normalized = list(holdings)
            # Preserve imported vs manual split
            _c_ec.holdings_imported   = [h for h in holdings if h.get("entry_mode","manual") != "manual_extra"]
            _CS_ec.save(_c_ec)
        except Exception:
            pass
    return changed


# ── Add manual product form ───────────────────────────────────────────────────

def _render_add_form(holdings: list[dict], df_long: pd.DataFrame) -> bool:
    """
    Dual-mode product-addition form.
    Catalog-supported types (קרן השתלמות, פוליסת חיסכון, …) → guided selectbox flow.
    External/manual types (נדלן, קריפטו, …) → free-text form.
    Returns False (additions happen inside sub-functions via st.rerun).
    """
    with st.expander("➕ הוסף מוצר", expanded=False):

        product_type_raw = st.selectbox(
            "סוג מוצר",
            ALL_PRODUCT_TYPES,
            format_func=lambda x: ("📚 " + x if x in SUPPORTED_CATALOG_TYPES else "✏️ " + x),
            key="pf_add_type",
        )
        product_type = normalize_product_type(product_type_raw)
        _is_catalog  = is_catalog_supported(product_type)

        badge_html = (
            '<div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:7px;'
            'padding:6px 12px;font-size:11.5px;color:#1e40af;direction:rtl;margin-bottom:8px">'
            '📚 בחירה מתוך קטלוג האפליקציה</div>'
            if _is_catalog else
            '<div style="background:#fef3c7;border:1px solid #fde68a;'
            'border-right:3px solid #f59e0b;border-radius:7px;'
            'padding:6px 12px;font-size:11.5px;color:#92400e;direction:rtl;margin-bottom:8px">'
            '✏️ מוצר חיצוני — הזנה ידנית מלאה</div>'
        )
        st.markdown(badge_html, unsafe_allow_html=True)

        if _is_catalog:
            _form_catalog(holdings, df_long, product_type)
        else:
            _form_manual(holdings, product_type)

    return False


def _form_catalog(holdings: list[dict], df_long: pd.DataFrame, product_type: str) -> None:
    """Catalog-driven form: manager → fund → track → auto-fill allocations."""
    managers = get_catalog_managers(df_long)
    if not managers:
        st.warning(
            "אין נתוני קטלוג בטאב הנוכחי. "
            "בחר את הטאב המתאים (קרנות השתלמות, פוליסות...) — או עבור להזנה ידנית:"
        )
        _form_manual(holdings, product_type)
        return

    c1, c2 = st.columns(2)
    with c1:
        manager = st.selectbox("גוף מנהל", managers, key="pf_cat_mgr")
    funds = get_catalog_funds(df_long, manager)
    with c2:
        if funds:
            fund = st.selectbox("שם קרן / מוצר", funds, key="pf_cat_fund")
        else:
            fund = st.text_input("שם קרן / מוצר", key="pf_cat_fund_txt", placeholder=manager)

    tracks = get_catalog_tracks(df_long, manager, fund)
    c3, c4 = st.columns(2)
    with c3:
        if tracks:
            track = st.selectbox("מסלול", tracks, key="pf_cat_track")
        else:
            track = st.text_input("מסלול", key="pf_cat_track_txt", placeholder="כללי, מנייתי...")
    with c4:
        amount = st.number_input("סכום (₪)", min_value=0.0, step=1000.0, key="pf_cat_amount")
    notes = st.text_input("הערות (אופציונלי)", key="pf_cat_notes")

    preview = get_catalog_preview(df_long, manager, fund, track)
    override: dict = {}

    if preview:
        def _pf(v): return "{:.1f}%".format(v) if v is not None else "—"
        lbl = "לפי קרן" if preview.get("matched_by") == "fund" else "לפי מנהל"
        msg = (
            "נמצאו נתונים (" + lbl + "): "
            "מניות " + _pf(preview.get("equity_pct")) +
            " | חוץ " + _pf(preview.get("foreign_pct")) +
            " | סחיר " + _pf(preview.get("illiquid_pct"))
        )
        st.success("💡 " + msg)
    else:
        st.info("לא נמצאו נתוני הקצאה — ניתן להזין ידנית למטה.")

    with st.expander("✏️ עריכה ידנית של תמהיל (אופציונלי)", expanded=(preview is None)):
        def _def(k): return float(preview[k]) if preview and preview.get(k) is not None else 0.0
        a1,a2,a3,a4,a5 = st.columns(5)
        override["equity_pct"]   = a1.number_input("מניות %",   0.0, 100.0, _def("equity_pct"),   key="pf_cat_eq")
        override["foreign_pct"]  = a2.number_input("חול %",     0.0, 100.0, _def("foreign_pct"),  key="pf_cat_fo")
        override["fx_pct"]       = a3.number_input("מטח %",     0.0, 100.0, _def("fx_pct"),       key="pf_cat_fx")
        override["illiquid_pct"] = a4.number_input("לא-סחיר %", 0.0, 100.0, _def("illiquid_pct"), key="pf_cat_ill")
        override["sharpe"]       = a5.number_input("שארפ",      0.0,  5.0,  _def("sharpe"),       key="pf_cat_sh",
                                                    step=0.01, format="%.2f")
        _has_override = any(v > 0 for v in override.values())

    if st.button("➕ הוסף לפורטפוליו", key="pf_cat_submit", type="primary"):
        if amount <= 0:
            st.error("יש להזין סכום חיובי.")
            return
        def _pick(k):
            if _has_override: return override.get(k) or None
            return preview.get(k) if preview else None
        new_h = make_manual_holding(
            product_type         = product_type,
            provider             = manager,
            product_name         = fund or manager,
            track                = track,
            amount               = amount,
            equity               = _pick("equity_pct"),
            foreign              = _pick("foreign_pct"),
            fx                   = _pick("fx_pct"),
            illiquid             = _pick("illiquid_pct"),
            sharpe               = _pick("sharpe"),
            notes                = notes,
            entry_mode           = "catalog",
            catalog_reference_id = fund or manager,
        )
        holdings.append(new_h)
        set_holdings(st, holdings)
        # Sync to CaseStore so workflow validation stays consistent
        try:
            from case_management.case_store import CaseStore as _CS
            _c = _CS.get()
            _c.holdings_normalized = list(holdings)
            _c.holdings_imported   = list(holdings)
            from case_management import STEP_DATA_INTAKE
            _c.step_done[STEP_DATA_INTAKE] = True
            _CS.save(_c)
        except Exception:
            pass
        st.success("✅ " + new_h["product_name"] + " (" + track + ") נוסף.")
        st.rerun()


def _form_manual(holdings: list[dict], product_type: str) -> None:
    """Free-text form for external/manual product types."""
    c1, c2, c3 = st.columns(3)
    provider     = c1.text_input("גוף מנהל / ברוקר", key="pf_man_prov",
                                  placeholder="הראל, Schwab, בנק לאומי...")
    product_name = c2.text_input("שם מוצר / נכס",    key="pf_man_name",
                                  placeholder="שם, ISIN, כינוי...")
    track        = c3.text_input("מסלול / תיאור",    key="pf_man_track",
                                  placeholder="ישיר, ינואר 24...")
    c4, c5 = st.columns(2)
    amount = c4.number_input("סכום (₪)", min_value=0.0, step=1000.0, key="pf_man_amt")
    notes  = c5.text_input("הערות",                  key="pf_man_notes")

    with st.expander("📊 תמהיל / חשיפות (אופציונלי)", expanded=False):
        a1,a2,a3,a4,a5 = st.columns(5)
        eq  = a1.number_input("מניות %",   0.0, 100.0, 0.0, key="pf_man_eq")
        fo  = a2.number_input("חול %",     0.0, 100.0, 0.0, key="pf_man_fo")
        fx  = a3.number_input("מטח %",     0.0, 100.0, 0.0, key="pf_man_fx")
        ill = a4.number_input("לא-סחיר %", 0.0, 100.0, 0.0, key="pf_man_ill")
        sh  = a5.number_input("שארפ",      0.0,  5.0,  0.0, key="pf_man_sh",
                               step=0.01, format="%.2f")

    if st.button("➕ הוסף לפורטפוליו", key="pf_man_submit", type="primary"):
        if amount <= 0:
            st.error("יש להזין סכום חיובי.")
            return
        # For manual/external types, product_name can default to product_type if empty
        _name = product_name or provider or product_type
        new_h = make_manual_holding(
            product_type = product_type,
            provider     = provider or _name,
            product_name = _name,
            track        = track,
            amount       = amount,
            equity       = eq  if eq  > 0 else None,
            foreign      = fo  if fo  > 0 else None,
            fx           = fx  if fx  > 0 else None,
            illiquid     = ill if ill > 0 else None,
            sharpe       = sh  if sh  > 0 else None,
            notes        = notes,
            entry_mode   = "manual",
        )
        holdings.append(new_h)
        set_holdings(st, holdings)
        # Sync to CaseStore
        try:
            from case_management.case_store import CaseStore as _CS2
            _c2 = _CS2.get()
            _c2.holdings_normalized = list(holdings)
            _c2.holdings_imported   = list(holdings)
            from case_management import STEP_DATA_INTAKE
            _c2.step_done[STEP_DATA_INTAKE] = True
            _CS2.save(_c2)
        except Exception:
            pass
        st.success("✅ " + new_h["product_name"] + " נוסף לפורטפוליו.")
        st.rerun()


# ── Import from clearinghouse shortcut ───────────────────────────────────────

def _render_import_bar(holdings: list[dict], df_long: pd.DataFrame, product_type: str) -> bool:
    """Import button that pulls from the existing clearinghouse session state."""
    raw = st.session_state.get("portfolio_holdings") or []
    if not raw:
        return False

    existing_keys = {
        (h["provider"].lower(), h["product_name"].lower())
        for h in holdings
    }
    new_count = sum(
        1 for r in raw
        if (str(r.get("manager","")).lower(), str(r.get("fund","")).lower())
           not in existing_keys
    )

    if new_count == 0:
        st.caption(f"✅ {len(raw)} רשומות מהמסלקה כבר מיובאות.")
        return False

    import streamlit as _st
    if st.button(
        f"📥 ייבא {new_count} מוצרים מדו\"ח המסלקה לפורטפוליו",
        key="pf_import_btn",
    ):
        import streamlit as st2
        added = import_from_session(st2, df_long, product_type)
        if added:
            st.toast(f"✅ {added} מוצרים יובאו בהצלחה")
            return True
    return False


# ── What-if integration ───────────────────────────────────────────────────────

def _render_whatif(holdings: list[dict]) -> None:
    """
    Build a what-if baseline from portfolio and inject it into the optimizer.
    Respects locked / excluded flags.
    """
    if not holdings:
        return

    active = [h for h in holdings if not h.get("excluded", False)]
    if not active:
        st.info("כל המוצרים מוחרגים — אין בסיס לניתוח what-if.")
        return

    locked = [h for h in active if h.get("locked",  False)]
    free   = [h for h in active if not h.get("locked", False)]

    st.markdown("---")
    st.markdown("### 🔀 What-If — שימוש בפורטפוליו כבסיס לאופטימיזציה")

    lc1, lc2, lc3 = st.columns(3)
    lc1.metric("מוצרים פעילים", len(active))
    lc2.metric("נעולים (לא ישתנו)", len(locked))
    lc3.metric("פנויים לאופטימיזציה", len(free))

    if locked:
        st.caption(
            "**מוצרים נעולים** יישמרו בתיק ללא שינוי. "
            "האופטימיזציה תחפש הרכב מיטבי רק עבור המוצרים הפנויים."
        )
        locked_df = pd.DataFrame([{
            "גוף":    h["provider"],
            "מוצר":   h["product_name"],
            "מסלול":  h["track"],
            "סכום":   _fmt_amount(h["amount"]),
            "מניות":  _nan_str(h.get("equity_pct")),
            'חו"ל':   _nan_str(h.get("foreign_pct")),
        } for h in locked])
        st.dataframe(locked_df, use_container_width=True, hide_index=True)

    if not any(
        not math.isnan(h.get("equity_pct", float("nan")))
        for h in active
    ):
        st.warning(
            "⚠️ לא ניתן לחשב בסיס — אין נתוני אלוקציה. "
            "מלא תמהיל לפחות לחלק מהמוצרים."
        )
        return

    if st.button(
        "🚀 שלח לאופטימיזציה כפורטפוליו בסיס",
        key="pf_whatif_submit",
        type="primary",
        help="מחשב תמהיל משוקלל ושומר כ-baseline לאופטימיזציה הראשית",
    ):
        baseline = build_whatif_baseline(active)
        st.session_state["portfolio_baseline"] = baseline
        st.session_state["portfolio_total"] = sum(h["amount"] for h in active)
        st.session_state["portfolio_managers"] = list({h["provider"] for h in active})

        # Pre-fill optimizer targets from baseline
        if "targets" in st.session_state:
            if baseline.get("stocks"):
                st.session_state["targets"]["stocks"]   = round(baseline["stocks"], 1)
            if baseline.get("foreign"):
                st.session_state["targets"]["foreign"]  = round(baseline["foreign"], 1)
            if baseline.get("fx"):
                st.session_state["targets"]["fx"]       = round(baseline["fx"], 1)
            if baseline.get("illiquid"):
                st.session_state["targets"]["illiquid"] = round(baseline["illiquid"], 1)

        st.success(
            f"✅ הבסיס נשמר: "
            f"מניות {baseline.get('stocks',0):.1f}% | "
            f"חו\"ל {baseline.get('foreign',0):.1f}% | "
            f"מט\"ח {baseline.get('fx',0):.1f}% | "
            f"לא סחיר {baseline.get('illiquid',0):.1f}%\n\n"
            "גלול למעלה לאופטימיזציה."
        )


# ── Main entry point ──────────────────────────────────────────────────────────

def render_portfolio_analysis(df_long: pd.DataFrame, product_type: str) -> None:
    """
    Render the full portfolio analysis module as an st.expander.
    Call once at the bottom of streamlit_app.py, after render_history().
    """
    with st.expander("💼 ניתוח פורטפוליו נוכחי של כלל המוצרים", expanded=False):

        holdings = get_holdings(st)

        # ── Top bar: import from clearinghouse ────────────────────────────
        if _render_import_bar(holdings, df_long, product_type):
            set_holdings(st, get_holdings(st))
            st.rerun()

        # ── Summary metrics ───────────────────────────────────────────────
        df = holdings_to_df(holdings)
        if not df.empty:
            summary = compute_portfolio_summary(df)
            st.markdown(
                "<div style='font-size:11px;font-weight:700;color:#1F3A5F;margin-bottom:4px;direction:rtl'>"
                "📊 התמהיל המשוקלל של כלל הפרוטפוליו</div>",
                unsafe_allow_html=True,
            )
            _render_summary_metrics(summary)

        st.markdown("---")

        # ── Main tabs ─────────────────────────────────────────────────────
        t_table, t_edit, t_add = st.tabs([
            "📋 טבלת פורטפוליו",
            "✏️ עריכה וניהול",
            "➕ הוסף מוצר",
        ])

        with t_table:
            _render_portfolio_table(holdings, df_long)
            if not df.empty:
                # Export
                exp_df = df.rename(columns={
                    "provider": "גוף", "product_name": "מוצר", "track": "מסלול",
                    "product_type": "סוג", "amount": "סכום", "weight": "משקל %",
                    "equity_pct": "מניות %", "foreign_pct": 'חו"ל %',
                    "fx_pct": 'מט"ח %', "illiquid_pct": "לא סחיר %",
                    "sharpe": "שארפ", "notes": "הערות", "source_type": "מקור",
                })
                st.download_button(
                    "⬇️ ייצוא CSV",
                    data=exp_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
                    file_name="portfolio.csv", mime="text/csv",
                    key="pf_dl",
                )

        with t_edit:
            if _render_edit_controls(holdings, df_long):
                set_holdings(st, holdings)
                st.rerun()

            # Auto-fill all missing
            missing = [h for h in holdings if h.get("allocation_source") == "missing"]
            if missing:
                st.markdown("---")
                if st.button(
                    f"🔄 מלא אוטומטית את כל {len(missing)} המוצרים החסרים",
                    key="pf_autofill_all",
                ):
                    for i, h in enumerate(holdings):
                        if h.get("allocation_source") == "missing":
                            holdings[i] = try_autofill(h, df_long)
                    set_holdings(st, holdings)
                    st.rerun()

            # Clear all
            st.markdown("---")
            if holdings and st.button("🗑️ נקה פורטפוליו כולו", key="pf_clear_all"):
                set_holdings(st, [])
                st.rerun()

        with t_add:
            if _render_add_form(holdings, df_long):
                set_holdings(st, holdings)
                st.rerun()
