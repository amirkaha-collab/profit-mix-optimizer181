# -*- coding: utf-8 -*-
"""
institutional_strategy_analysis/ui.py
───────────────────────────────────────
Self-contained Streamlit UI for "ניתוח אסטרטגיות מוסדיים".
Renders as an st.expander at the bottom of the main app.

Entry point (one line in streamlit_app.py):
    from institutional_strategy_analysis.ui import render_institutional_analysis
    render_institutional_analysis()

All session-state keys are prefixed "isa_" to avoid any collision.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

# ── Sheet URL ─────────────────────────────────────────────────────────────────
# ▼▼▼  Set your Google Sheets URL here  ▼▼▼
ISA_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1e9zjj1OWMYqUYoK6YFYvYwOnN7qbydYDyArHbn8l9pE/edit"
)
# ▲▲▲─────────────────────────────────────────────────────────────────────────

# ── Lazy imports (never execute at import time) ───────────────────────────────

def _load_data():
    from institutional_strategy_analysis.loader     import load_raw_blocks
    from institutional_strategy_analysis.series_builder import get_time_bounds
    import streamlit as st

    @st.cache_data(ttl=3600, show_spinner=False)
    def _cached(url: str):
        return load_raw_blocks(url)

    return _cached(ISA_SHEET_URL)


def _build_series(df_y, df_m, rng, custom_start, filters):
    from institutional_strategy_analysis.series_builder import build_display_series
    return build_display_series(df_y, df_m, rng, custom_start, filters)


def _options(df_y, df_m):
    from institutional_strategy_analysis.series_builder import get_available_options
    return get_available_options(df_y, df_m)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_plotly(fig, key=None):
    try:
        st.plotly_chart(fig, use_container_width=True, key=key)
    except TypeError:
        st.plotly_chart(fig)


def _csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def _clamp(val: date, lo: date, hi: date) -> date:
    return max(lo, min(hi, val))


# ── Debug panel ───────────────────────────────────────────────────────────────

def _render_debug(df_yearly, df_monthly, debug_info, errors):
    # Hidden from users — kept for developer reference only
    pass



# ── AI Analysis renderer ──────────────────────────────────────────────────────

_SECTION_ICONS = {
    # Market analysis
    "מיצוב יחסי לפי רכיב":                           "🎯",
    "דינמיות ואפיון סגנון ניהול":                    "⚡",
    'אסטרטגיית גידור מט"ח':                          "🛡️",
    "תנועות פוזיציה אחרונות (3–12 חודשים)":          "🔄",
    "ניתוח סיכון קבוצתי":                            "⚠️",
    "יתרונות וחסרונות לפי גוף":                      "✅",
    "תובנה אסטרטגית וסיכום":                         "💡",
    # Focused analysis
    "מיצוב יחסי (Relative Positioning)":             "🎯",
    "ניתוח היסטורי עצמי (Historical Self-Analysis)": "📜",
    "סגנון ניהול ועקביות (Management Style & Consistency)": "⚡",
    "אסטרטגיית גידור ומטבע (Hedging & Currency Strategy)": "🛡️",
    "מומנטום ותנועות אחרונות (Recent Momentum)":     "🔄",
    "פרופיל סיכון (Risk Assessment)":                "⚠️",
    "גזר דין — בחירת מנהל (Manager Selection Verdict)": "👑",
    # Comparison
    "סיכום מנהלי (Executive Summary)":               "📌",
    "השוואה יחסית לפי רכיב":                        "⚖️",
    "הבדלי סגנון ניהול (Management Style Delta)":    "⚡",
    "אסטרטגיית גידור (Hedging Comparison)":         "🛡️",
    "המלצה לפי פרופיל משקיע":                       "👤",
    # Legacy fallbacks
    "ניתוח לפי גוף ומסלול":    "🏢",
    "ניתוח סיכון":              "⚠️",
    "תובנה אסטרטגית":          "💡",
    "סיכום מנהלי":             "📌",
}

_EXPANDED_SECTIONS = {
    "מיצוב יחסי",
    "סיכום מנהלי",
    "גזר דין",
    "תובנה אסטרטגית",
}


def _render_api_key_input():
    """Returns True if OPENAI_API_KEY is available in Streamlit Secrets. No user input needed."""
    try:
        if hasattr(st, "secrets") and "OPENAI_API_KEY" in st.secrets:
            return True
    except Exception:
        pass
    st.error("⚠️ לא הוגדר מפתח OPENAI_API_KEY ב-Streamlit Secrets. יש להוסיפו תחת Settings → Secrets.")
    return False


def _render_analysis_result(result, cache_key: str, dl_key: str, refresh_key: str,
                             auto_expand: bool = False):
    """Display an AnalysisResult with styled section expanders."""
    if result.error:
        st.error(f"⚠️ {result.error}")
        if st.button("נסה שוב", key=f"{refresh_key}_retry_{cache_key}"):
            st.session_state.pop(cache_key, None)
            st.session_state.pop(f"{cache_key}_sig", None)
            st.rerun()
        return

    if not result.sections:
        st.markdown(result.raw_text)
    else:
        for title, body in result.sections.items():
            if title == "כללי" and not body.strip():
                continue
            icon = _SECTION_ICONS.get(title, "📋")
            # auto_expand opens every section; otherwise use default logic
            exp = auto_expand or any(s in title for s in _EXPANDED_SECTIONS)
            with st.expander(f"{icon} {title}", expanded=exp):
                st.markdown(body)

    col_dl, col_rf, _ = st.columns([1, 1, 4])
    with col_dl:
        st.download_button(
            "⬇️ שמור ניתוח",
            data=result.raw_text.encode("utf-8"),
            file_name=f"{dl_key}.txt",
            mime="text/plain",
            key=f"isa_dl_{dl_key}_{cache_key}",
            use_container_width=True,
        )
    with col_rf:
        if st.button("🔄 רענן", key=f"{refresh_key}_{cache_key}",
                     help="הרץ מחדש את הניתוח", use_container_width=True):
            st.session_state.pop(cache_key, None)
            st.session_state.pop(f"{cache_key}_sig", None)
            st.rerun()


def _scorecard_badge(diff: float) -> str:
    """Return an HTML badge for relative positioning."""
    if diff > 3:   return "<span style='background:#16a34a;color:#fff;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700'>▲ גבוה משמעותית</span>"
    if diff > 1:   return "<span style='background:#4ade80;color:#14532d;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700'>▲ מעל ממוצע</span>"
    if diff < -3:  return "<span style='background:#dc2626;color:#fff;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700'>▼ נמוך משמעותית</span>"
    if diff < -1:  return "<span style='background:#f87171;color:#7f1d1d;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700'>▼ מתחת לממוצע</span>"
    return "<span style='background:#e2e8f0;color:#475569;padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700'>◼ ממוצע</span>"


def _direction_badge(direction: str) -> str:
    if direction == "עולה":   return "🟢 עולה"
    if direction == "יורדת":  return "🔴 יורדת"
    return "⚪ יציבה"


def _render_quick_scorecard(full_df: pd.DataFrame, manager: str, track: str):
    """Render a quick stat-based scorecard card before running AI."""
    import numpy as np
    try:
        from institutional_strategy_analysis.ai_analyst import compute_manager_scorecard
        rows = compute_manager_scorecard(full_df, manager, track)
    except Exception:
        return

    if not rows:
        return

    st.markdown("""
<div style='background:#f0f4ff;border:1px solid #c7d7fe;border-radius:10px;
     padding:14px 18px;margin:10px 0 4px 0;direction:rtl'>
  <div style='font-size:13px;font-weight:700;color:#1e3a8a;margin-bottom:10px'>
    📊 סקירה מהירה — מיצוב יחסי לפי רכיב
  </div>""", unsafe_allow_html=True)

    cols = st.columns(len(rows))
    for col, row in zip(cols, rows):
        diff = row["diff_mean"]
        c3   = row.get("change_3m", float("nan"))
        c12  = row.get("change_12m", float("nan"))
        import math
        c3s  = f"{c3:+.1f}pp" if not math.isnan(c3)  else "—"
        c12s = f"{c12:+.1f}pp" if not math.isnan(c12) else "—"
        with col:
            st.markdown(f"""
<div style='background:#fff;border:1px solid #e2e8f0;border-radius:8px;
     padding:10px;text-align:center;direction:rtl'>
  <div style='font-size:11px;color:#64748b;margin-bottom:4px'>{row['alloc']}</div>
  <div style='font-size:22px;font-weight:900;color:#1e3a8a'>{row['current']}%</div>
  <div style='font-size:11px;color:#64748b'>ממוצע קבוצה: {row['peer_mean']}%</div>
  <div style='font-size:11px;margin:4px 0'>{_scorecard_badge(diff)}</div>
  <div style='font-size:10px;color:#94a3b8;margin-top:4px'>
    3ח: {c3s} | 12ח: {c12s}<br/>
    דירוג: {row['rank']}/{row['n_total']} | {_direction_badge(row['direction'])}
  </div>
</div>""", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


def _render_ai_section(
    df_yearly,
    df_monthly,
    opts: dict,
    tab_df_long=None,
    tab_product_type=None,
):
    """
    Fully independent AI analysis panel.
    Has its own filters — ALL managers / ALL tracks / ALL allocs by default.
    Modes: ניתוח שוק | ניתוח מיקוד | השוואה ישירה | שיחה חופשית
    """
    st.markdown("---")
    st.markdown("""
<div style='background:linear-gradient(135deg,#0f2657 0%,#1d4ed8 60%,#2563eb 100%);
     border-radius:14px;padding:18px 24px;margin-bottom:18px;direction:rtl'>
  <div style='color:#fff;font-size:20px;font-weight:900;letter-spacing:-0.5px'>
    🤖 מנוע ניתוח AI — אסטרטגיות מוסדיים
  </div>
  <div style='color:#93c5fd;font-size:12px;margin-top:5px;line-height:1.6'>
    מיצוב יחסי · היסטוריה עצמית · גידור מט"ח · סגנון ניהול · בחירת מנהל · שיחה חופשית
  </div>
  <div style='display:flex;gap:8px;margin-top:10px;flex-wrap:wrap'>
    <span style='background:rgba(255,255,255,.15);color:#e0eaff;padding:3px 10px;
      border-radius:99px;font-size:11px'>CIO Level Analysis</span>
    <span style='background:rgba(255,255,255,.15);color:#e0eaff;padding:3px 10px;
      border-radius:99px;font-size:11px'>Manager Selection</span>
    <span style='background:rgba(255,255,255,.15);color:#e0eaff;padding:3px 10px;
      border-radius:99px;font-size:11px'>Relative Positioning</span>
  </div>
</div>""", unsafe_allow_html=True)

    # ── API key ───────────────────────────────────────────────────────────
    has_key = _render_api_key_input()
    if not has_key:
        return

    # ── AI-specific filters (independent from chart filters) ──────────────
    with st.expander("🎛️ הגדרות ניתוח AI", expanded=False):
        ai_fc1, ai_fc2, ai_fc3, ai_fc4 = st.columns(4)
        with ai_fc1:
            ai_mgrs = st.multiselect(
                "גופים לניתוח AI",
                options=opts["managers"],
                default=opts["managers"],
                key="isa_ai_managers",
                help="ברירת מחדל: כל הגופים",
            )
        all_ai_tracks = sorted({
            t for df in (df_yearly, df_monthly) if not df.empty
            for t in df[df["manager"].isin(ai_mgrs)]["track"].unique()
        }) if ai_mgrs else opts["tracks"]
        with ai_fc2:
            ai_tracks = st.multiselect(
                "מסלולים",
                options=all_ai_tracks,
                default=all_ai_tracks,
                key="isa_ai_tracks",
                help="ברירת מחדל: כל המסלולים",
            )
        all_ai_allocs = sorted({
            a for df in (df_yearly, df_monthly) if not df.empty
            for a in df[
                df["manager"].isin(ai_mgrs) & df["track"].isin(ai_tracks)
            ]["allocation_name"].unique()
        }) if ai_mgrs and ai_tracks else opts["allocation_names"]
        with ai_fc3:
            ai_allocs = st.multiselect(
                "רכיבי אלוקציה",
                options=all_ai_allocs,
                default=all_ai_allocs,
                key="isa_ai_allocs",
                help="ברירת מחדל: כל הרכיבים",
            )
        with ai_fc4:
            ai_range = st.selectbox(
                "טווח זמן",
                options=["הכל", "5Y", "3Y", "1Y"],
                index=0,
                key="isa_ai_range",
            )

    if not ai_mgrs or not ai_tracks or not ai_allocs:
        st.info("יש לבחור לפחות גוף, מסלול ורכיב אחד לניתוח AI.")
        return

    # Build AI dataset — all managers, independent of chart filters
    ai_filters = {"managers": ai_mgrs, "tracks": ai_tracks, "allocation_names": ai_allocs}
    try:
        ai_df = _build_series(df_yearly, df_monthly, ai_range, None, ai_filters)
    except Exception:
        ai_df = pd.DataFrame()

    if ai_df.empty:
        st.warning("אין נתונים לניתוח AI עם הפילטרים הנוכחיים.")
        return

    # full_df = ALL managers (for peer comparisons in focused mode)
    full_ai_filters = {
        "managers":         opts["managers"],
        "tracks":           ai_tracks,
        "allocation_names": ai_allocs,
    }
    try:
        full_ai_df = _build_series(df_yearly, df_monthly, ai_range, None, full_ai_filters)
    except Exception:
        full_ai_df = ai_df

    ai_context = {
        "managers":         ai_mgrs,
        "tracks":           ai_tracks,
        "allocation_names": ai_allocs,
        "selected_range":   ai_range,
        "date_min":         ai_df["date"].min().strftime("%Y-%m") if not ai_df.empty else "",
        "date_max":         ai_df["date"].max().strftime("%Y-%m") if not ai_df.empty else "",
    }

    # ── Mode selector ─────────────────────────────────────────────────────
    mode_labels = {
        "market":     "🌐 ניתוח שוק",
        "focused":    "🎯 ניתוח מיקוד",
        "headtohead": "⚖️ השוואה ישירה",
        "chat":       "💬 שיחה חופשית",
    }
    mode_idx = st.session_state.get("isa_ai_mode_idx", 0)

    mode_cols = st.columns(4)
    for col, (k, label), idx in zip(mode_cols, mode_labels.items(), range(4)):
        selected = (mode_idx == idx)
        bg  = "linear-gradient(135deg,#1d4ed8,#2563eb)" if selected else "#f8faff"
        txt = "#ffffff" if selected else "#1e3a8a"
        brd = "#1d4ed8" if selected else "#c7d7fe"
        with col:
            st.markdown(f"""
<div style='background:{bg};border:2px solid {brd};border-radius:10px;
     padding:9px 8px;text-align:center;direction:rtl;color:{txt};
     font-size:13px;font-weight:600;margin-bottom:6px'>{label}</div>""",
                unsafe_allow_html=True)
            if st.button(
                "✓ פעיל" if selected else "בחר",
                key=f"isa_mode_{k}",
                type="primary" if selected else "secondary",
                use_container_width=True,
            ):
                st.session_state["isa_ai_mode_idx"] = idx
                st.rerun()

    st.markdown("<hr style='border:none;border-top:1px solid #e2e8f0;margin:10px 0'>",
                unsafe_allow_html=True)

    all_combos = sorted(
        full_ai_df[["manager", "track"]].drop_duplicates()
        .apply(lambda r: f"{r['manager']} | {r['track']}", axis=1)
        .tolist()
    ) if not full_ai_df.empty else []
    all_mgrs_list = sorted(full_ai_df["manager"].unique().tolist()) if not full_ai_df.empty else ai_mgrs

    # ══════════════════════════════════════════════════════════════════════
    # MODE 0 — Market Analysis
    # ══════════════════════════════════════════════════════════════════════
    if mode_idx == 0:
        st.markdown("""
<div style='background:#f0f9ff;border-right:4px solid #1d4ed8;padding:10px 16px;
     border-radius:0 8px 8px 0;margin-bottom:14px;direction:rtl'>
  <b style='color:#1e3a8a'>ניתוח שוק</b>
  <span style='color:#475569;font-size:12px'> — ניתוח יחסי בין כל הגופים: מיצוב, דינמיות, גידור מט"ח, סיכון</span>
</div>""", unsafe_allow_html=True)

        cache_key  = "isa_market_result"
        filter_sig = f"{ai_mgrs}|{ai_tracks}|{ai_allocs}|{ai_range}"
        if st.session_state.get("isa_market_sig") != filter_sig:
            st.session_state.pop(cache_key, None)
            st.session_state["isa_market_sig"] = filter_sig
            st.session_state.pop("isa_market_just_done", None)

        if cache_key not in st.session_state:
            st.caption(f"גופים: {', '.join(ai_mgrs)} | מסלולים: {', '.join(ai_tracks)}")
            st.markdown("""
<style>div[data-testid="stButton"] button[kind="primary"] {
  font-size:16px !important; padding:12px 24px !important;
  font-weight:800 !important; letter-spacing:0.3px;
}</style>""", unsafe_allow_html=True)
            if st.button("🌐 הפעל ניתוח שוק", key="isa_market_btn", type="primary"):
                with st.spinner("AI מנתח השוואה בין גופים... (עד 90 שניות)"):
                    try:
                        from institutional_strategy_analysis.ai_analyst import run_ai_analysis
                        result = run_ai_analysis(ai_df, ai_context)
                        st.session_state[cache_key] = result
                        st.session_state["isa_market_just_done"] = True
                    except Exception as e:
                        st.error(f"שגיאה: {e}")
                        return
                st.rerun()
        else:
            st.caption(f"גופים: {', '.join(ai_mgrs)} | מסלולים: {', '.join(ai_tracks)}")
            auto_exp = st.session_state.pop("isa_market_just_done", False)
            _render_analysis_result(
                st.session_state[cache_key],
                cache_key, "market_analysis", "isa_market_refresh",
                auto_expand=auto_exp,
            )

    # ══════════════════════════════════════════════════════════════════════
    # MODE 1 — Focused Single-Manager Analysis
    # ══════════════════════════════════════════════════════════════════════
    elif mode_idx == 1:
        st.markdown("""
<div style='background:#f0fdf4;border-right:4px solid #16a34a;padding:10px 16px;
     border-radius:0 8px 8px 0;margin-bottom:14px;direction:rtl'>
  <b style='color:#14532d'>ניתוח מיקוד</b>
  <span style='color:#475569;font-size:12px'> — גוף אחד לעומת כל עמיתיו: מיצוב יחסי, היסטוריה, סגנון, גזר דין</span>
</div>""", unsafe_allow_html=True)

        f1, f2 = st.columns(2)
        with f1:
            focus_mgr = st.selectbox(
                "גוף מנהל לניתוח",
                options=all_mgrs_list,
                index=0,
                key="isa_focus_mgr",
                help="ינותח לעומק מול כלל עמיתיו",
            )
        avail_tracks_focus = sorted(
            full_ai_df[full_ai_df["manager"] == focus_mgr]["track"].unique().tolist()
        ) if not full_ai_df.empty else ai_tracks
        with f2:
            focus_trk = st.selectbox(
                "מסלול",
                options=avail_tracks_focus if avail_tracks_focus else ai_tracks,
                index=0,
                key="isa_focus_trk",
            )

        # Peer group — all other managers by default, optional customisation
        peer_options = [m for m in all_mgrs_list if m != focus_mgr]
        use_custom_peers = st.toggle(
            "הגבל קבוצת ייחוס לגופים ספציפיים",
            value=False,
            key="isa_custom_peers_toggle",
            help="ברירת מחדל — כל הגופים האחרים",
        )
        custom_peers = None
        if use_custom_peers and peer_options:
            custom_peers = st.multiselect(
                "גופי ייחוס (peer group)",
                options=peer_options,
                default=peer_options,
                key="isa_focus_peers",
            )
            if not custom_peers:
                st.warning("יש לבחור לפחות גוף אחד לקבוצת הייחוס.")
                return

        # Quick scorecard (no API)
        _render_quick_scorecard(full_ai_df if not full_ai_df.empty else ai_df, focus_mgr, focus_trk)

        peer_str  = "|".join(sorted(custom_peers)) if custom_peers else "all"
        cache_key = f"isa_focus_{focus_mgr}_{focus_trk}_{peer_str}".replace(" ", "_")[:80]

        if cache_key not in st.session_state:
            peers_display = ", ".join(custom_peers) if custom_peers else f"כל הגופים ({len(peer_options)})"
            st.caption(f"קבוצת ייחוס: {peers_display}")
            # Prominent button
            if st.button(
                f"🎯 הפעל ניתוח מיקוד — {focus_mgr}",
                key="isa_focus_btn", type="primary",
                use_container_width=True,
            ):
                with st.spinner(f"AI מנתח {focus_mgr} לעומק... (עד 90 שניות)"):
                    try:
                        from institutional_strategy_analysis.ai_analyst import run_focused_analysis
                        fd = full_ai_df if not full_ai_df.empty else ai_df
                        focused_ctx = {**ai_context,
                                       "selected_manager": focus_mgr,
                                       "selected_track":   focus_trk}
                        result = run_focused_analysis(
                            fd, focus_mgr, focus_trk, custom_peers, focused_ctx
                        )
                        st.session_state[cache_key] = result
                        st.session_state["isa_focus_just_done"] = True
                    except Exception as e:
                        st.error(f"שגיאה: {e}")
                        return
                st.rerun()
        else:
            st.markdown(f"""
<div style='background:#f0fdf4;border:1px solid #86efac;border-radius:8px;
     padding:8px 14px;margin-bottom:8px;direction:rtl;font-size:13px;color:#14532d'>
  📋 ניתוח מיקוד: <b>{focus_mgr}</b> | מסלול: <b>{focus_trk}</b>
</div>""", unsafe_allow_html=True)
            auto_exp = st.session_state.pop("isa_focus_just_done", False)
            _render_analysis_result(
                st.session_state[cache_key],
                cache_key, f"focused_{focus_mgr[:8]}", "isa_focus_refresh",
                auto_expand=auto_exp,
            )

    # ══════════════════════════════════════════════════════════════════════
    # MODE 2 — Head-to-Head Comparison
    # ══════════════════════════════════════════════════════════════════════
    elif mode_idx == 2:
        st.markdown("""
<div style='background:#fff7ed;border-right:4px solid #ea580c;padding:10px 16px;
     border-radius:0 8px 8px 0;margin-bottom:14px;direction:rtl'>
  <b style='color:#7c2d12'>השוואה ישירה</b>
  <span style='color:#475569;font-size:12px'> — A מול B: יתרונות, חסרונות, המלצה לפי פרופיל משקיע</span>
</div>""", unsafe_allow_html=True)

        if len(all_combos) < 2:
            st.info("יש צורך בלפחות 2 גופים בנתוני ה-AI.")
            return

        cc1, cc2 = st.columns(2)
        with cc1:
            st.markdown("""<div style='background:#dbeafe;border-radius:8px 8px 0 0;
                padding:6px 12px;font-size:12px;font-weight:700;color:#1e40af;
                text-align:center;direction:rtl'>גוף A</div>""", unsafe_allow_html=True)
            combo_a = st.selectbox("גוף A", options=all_combos, index=0,
                                   key="isa_cmp_a", label_visibility="collapsed")
        with cc2:
            st.markdown("""<div style='background:#fef3c7;border-radius:8px 8px 0 0;
                padding:6px 12px;font-size:12px;font-weight:700;color:#92400e;
                text-align:center;direction:rtl'>גוף B</div>""", unsafe_allow_html=True)
            combo_b = st.selectbox("גוף B", options=all_combos,
                                   index=min(1, len(all_combos)-1),
                                   key="isa_cmp_b", label_visibility="collapsed")

        # Quick diff preview table
        if combo_a != combo_b:
            try:
                import numpy as np
                from institutional_strategy_analysis.ai_analyst import _compute_manager_profile
                mgr_a_p, trk_a_p = combo_a.split(" | ", 1)
                mgr_b_p, trk_b_p = combo_b.split(" | ", 1)
                pa = _compute_manager_profile(full_ai_df, mgr_a_p, trk_a_p)
                pb = _compute_manager_profile(full_ai_df, mgr_b_p, trk_b_p)
                if pa and pb:
                    shared = sorted(set(pa["per_alloc"]) & set(pb["per_alloc"]))
                    if shared:
                        preview_rows = []
                        for alloc in shared:
                            sa = pa["per_alloc"][alloc]
                            sb = pb["per_alloc"][alloc]
                            d  = sa["current"] - sb["current"]
                            preview_rows.append({
                                "רכיב": alloc,
                                f"{mgr_a_p}": f"{sa['current']}%",
                                f"{mgr_b_p}": f"{sb['current']}%",
                                "הפרש": f"{d:+.1f}pp",
                                "תזזיתי יותר": mgr_a_p if sa["dynamism"] > sb["dynamism"] else mgr_b_p,
                            })
                        if preview_rows:
                            st.dataframe(pd.DataFrame(preview_rows),
                                         use_container_width=True, hide_index=True)
            except Exception:
                pass

        cmp_cache = f"isa_cmp_{combo_a}_{combo_b}".replace(" ", "_").replace("|", "_")[:80]
        cmp_sig   = f"{combo_a}|{combo_b}"
        if st.session_state.get("isa_cmp_sig") != cmp_sig:
            for k in list(st.session_state.keys()):
                if k.startswith("isa_cmp_") and k not in ("isa_cmp_a", "isa_cmp_b", "isa_cmp_sig"):
                    st.session_state.pop(k, None)
            st.session_state["isa_cmp_sig"] = cmp_sig
            st.session_state.pop("isa_cmp_just_done", None)

        if cmp_cache not in st.session_state:
            if combo_a == combo_b:
                st.warning("יש לבחור שני גופים/מסלולים שונים.")
            else:
                if st.button("⚖️ הפעל השוואה", key="isa_cmp_btn",
                             type="primary", use_container_width=True):
                    mgr_a, trk_a = combo_a.split(" | ", 1)
                    mgr_b, trk_b = combo_b.split(" | ", 1)
                    with st.spinner(f"AI משווה {mgr_a} מול {mgr_b}... (עד 90 שניות)"):
                        try:
                            from institutional_strategy_analysis.ai_analyst import run_comparison_analysis
                            result = run_comparison_analysis(
                                full_ai_df, mgr_a, trk_a, mgr_b, trk_b, ai_context
                            )
                            st.session_state[cmp_cache] = result
                            st.session_state["isa_cmp_just_done"] = True
                        except Exception as e:
                            st.error(f"שגיאה: {e}")
                            return
                    st.rerun()
        else:
            mgr_a_l = combo_a.split(" | ", 1)[0]
            mgr_b_l = combo_b.split(" | ", 1)[0]
            st.markdown(f"""
<div style='display:flex;gap:10px;align-items:center;justify-content:center;
     margin:6px 0 12px 0;direction:rtl'>
  <span style='background:#dbeafe;color:#1e40af;font-weight:700;padding:4px 14px;
    border-radius:8px;font-size:13px'>{mgr_a_l}</span>
  <span style='color:#64748b;font-size:14px'>⚔️</span>
  <span style='background:#fef3c7;color:#92400e;font-weight:700;padding:4px 14px;
    border-radius:8px;font-size:13px'>{mgr_b_l}</span>
</div>""", unsafe_allow_html=True)
            auto_exp = st.session_state.pop("isa_cmp_just_done", False)
            _render_analysis_result(
                st.session_state[cmp_cache],
                cmp_cache, f"cmp_{mgr_a_l[:6]}_{mgr_b_l[:6]}", "isa_cmp_refresh",
                auto_expand=auto_exp,
            )

    # ══════════════════════════════════════════════════════════════════════
    # MODE 3 — Free Chat
    # ══════════════════════════════════════════════════════════════════════
    else:
        _render_ai_chat(full_ai_df, tab_df_long=tab_df_long, tab_product_type=tab_product_type,
                        active_df=ai_df)


def build_historical_ai_context(active_df: "pd.DataFrame") -> str:
    """
    Build a rich historical context from the ISA filtered time-series DataFrame
    (the same data used for the chart above the chat).

    active_df has columns: manager, track, date, frequency, allocation_name, allocation_value
    """
    import math
    try:
        if active_df is None or active_df.empty:
            return ""

        lines = ["=== נתוני סדרת הזמן המוצגת בתרשים ==="]

        managers   = sorted(active_df["manager"].dropna().unique().tolist())
        tracks     = sorted(active_df["track"].dropna().unique().tolist())
        allocs     = sorted(active_df["allocation_name"].dropna().unique().tolist())
        date_min   = active_df["date"].min().strftime("%Y-%m")
        date_max   = active_df["date"].max().strftime("%Y-%m")
        n_pts      = len(active_df)

        lines.append(f"גופים: {', '.join(managers)}")
        lines.append(f"מסלולים: {', '.join(tracks)}")
        lines.append(f"רכיבי אלוקציה: {', '.join(allocs)}")
        lines.append(f"טווח: {date_min} עד {date_max}  |  {n_pts:,} נקודות נתונים")
        lines.append("")

        # Per manager / track / allocation: statistics + trend
        grp_cols = ["manager", "track", "allocation_name"]
        for (mgr, trk, alloc), grp in active_df.groupby(grp_cols):
            series = grp.sort_values("date")["allocation_value"].dropna()
            if len(series) < 2:
                continue
            first_val  = round(float(series.iloc[0]), 2)
            last_val   = round(float(series.iloc[-1]), 2)
            min_val    = round(float(series.min()), 2)
            max_val    = round(float(series.max()), 2)
            delta      = round(last_val - first_val, 2)
            delta_str  = f"{delta:+.2f}pp"

            # Simple trend
            if len(series) >= 4:
                import numpy as np
                slope = float(np.polyfit(range(len(series)), series.values, 1)[0])
                if slope > 0.15:    trend = "↑ עלייה"
                elif slope < -0.15: trend = "↓ ירידה"
                else:               trend = "→ יציב"
            else:
                trend = "→ נתונים מועטים"

            lines.append(
                f"{mgr} | {trk} | {alloc}: "
                f"ראשון={first_val}%  אחרון={last_val}%  "
                f"מינ={min_val}%  מקס={max_val}%  "
                f"שינוי={delta_str}  מגמה={trend}"
            )

            # Short chronological excerpt (up to 8 points)
            dates_ser = grp.sort_values("date")[["date", "allocation_value"]].dropna()
            if len(dates_ser) <= 8:
                excerpt = "  ".join(
                    f"{row['date'].strftime('%Y-%m')}:{row['allocation_value']:.1f}%"
                    for _, row in dates_ser.iterrows()
                )
            else:
                # sample: first 3, middle 2, last 3
                head  = dates_ser.iloc[:3]
                mid   = dates_ser.iloc[len(dates_ser)//2 - 1 : len(dates_ser)//2 + 1]
                tail  = dates_ser.iloc[-3:]
                parts = pd.concat([head, mid, tail]).drop_duplicates()
                excerpt = "  ".join(
                    f"{row['date'].strftime('%Y-%m')}:{row['allocation_value']:.1f}%"
                    for _, row in parts.iterrows()
                ) + "  ..."
            lines.append(f"  סדרה: {excerpt}")

        lines.append("")
        lines.append(
            "אם המשתמש שואל על גוף/מסלול/רכיב שאינו ברשימה לעיל, "
            "ציין במפורש שהנתון אינו כלול בסינון הנוכחי."
        )
        return "\n".join(lines)
    except Exception as e:
        return f"(שגיאה בבניית הקשר היסטורי: {e})"


def build_tab_specific_ai_context(df_long, product_type, selected_managers=None) -> str:
    """
    Build a compact AI context string from the active tab's df_long.
    Returns empty string if df_long is None or empty.
    """
    import math
    try:
        if df_long is None or df_long.empty:
            return ""

        lines = [f"נתוני הטאב הפעיל — סוג מוצר: {product_type or 'לא ידוע'}"]
        lines.append(f"סך שורות: {len(df_long):,}")

        if "manager" in df_long.columns:
            managers = sorted(df_long["manager"].dropna().unique().tolist())
            lines.append(f"גופים מנהלים ({len(managers)}): {', '.join(managers)}")

        if "track" in df_long.columns:
            tracks = sorted(df_long["track"].dropna().unique().tolist())
            lines.append(f"מסלולים ({len(tracks)}): {', '.join(tracks)}")

        if "fund" in df_long.columns:
            n_funds = df_long["fund"].dropna().nunique()
            lines.append(f"קרנות/מוצרים ייחודיים: {n_funds}")

        if selected_managers:
            lines.append(f"מנהלים מסוננים: {', '.join(selected_managers)}")

        # Key numeric columns
        num_cols = [c for c in ["stocks", "foreign", "fx", "illiquid", "sharpe", "service"]
                    if c in df_long.columns]
        if num_cols:
            lines.append("עמודות חשיפה זמינות: " + ", ".join(num_cols))
            # Sample averages per manager if possible
            if "manager" in df_long.columns:
                try:
                    avg = df_long.groupby("manager")[num_cols].mean().round(1)
                    lines.append("ממוצעי חשיפה לפי מנהל:")
                    for mgr, row in avg.iterrows():
                        vals = "  ".join(
                            f"{c}={v:.1f}%" for c, v in row.items()
                            if not (isinstance(v, float) and math.isnan(v))
                        )
                        if vals:
                            lines.append(f"  {mgr}: {vals}")
                except Exception:
                    pass

        managers_list = (
            sorted(df_long["manager"].dropna().unique().tolist())
            if "manager" in df_long.columns else []
        )
        lines.append(
            "\nאם המשתמש שואל על גוף שאינו ברשימה לעיל, ציין במפורש "
            "שהגוף לא נמצא בנתוני הטאב הפעיל."
        )
        return "\n".join(lines)
    except Exception as e:
        return f"(שגיאה בבניית הקשר נתונים: {e})"


def _render_ai_chat(full_df: "pd.DataFrame", tab_df_long=None, tab_product_type=None,
                    active_df=None):
    """Free-form chat with the AI about the institutional data.

    Context priority (highest first):
      1. active_df  — the exact filtered ISA time-series shown in the chart
      2. tab_df_long — the parent-app df_long for the active product tab
      3. full_df / ISA-sheet summary — fallback
    """
    st.markdown("""
<div style='background:#f8faff;border:1px solid #c7d7fe;border-radius:12px;
     padding:16px 20px;margin-bottom:16px;direction:rtl'>
  <div style='font-size:15px;font-weight:800;color:#1e3a8a;margin-bottom:4px'>
    💬 שיחה חופשית עם AI
  </div>
  <div style='font-size:12px;color:#64748b'>
    שאל כל שאלה על הנתונים, על האסטרטגיות של הגופים, על מגמות, על בחירת מנהל
  </div>
</div>""", unsafe_allow_html=True)

    # ── Determine context source ──────────────────────────────────────────
    data_ctx    = ""
    ctx_source  = "ISA sheet (fallback)"
    ctx_mgrs    = []
    ctx_tracks  = []
    ctx_allocs  = []
    ctx_rows    = 0
    ctx_range   = "—"

    # Priority 1: active_df (ISA chart data)
    if active_df is not None and not active_df.empty:
        data_ctx   = build_historical_ai_context(active_df)
        ctx_source = "סדרת זמן ISA (תרשים פעיל)"
        ctx_rows   = len(active_df)
        if "manager" in active_df.columns:
            ctx_mgrs = sorted(active_df["manager"].dropna().unique().tolist())
        if "track" in active_df.columns:
            ctx_tracks = sorted(active_df["track"].dropna().unique().tolist())
        if "allocation_name" in active_df.columns:
            ctx_allocs = sorted(active_df["allocation_name"].dropna().unique().tolist())
        if "date" in active_df.columns:
            ctx_range = (
                f"{active_df['date'].min().strftime('%Y-%m')} – "
                f"{active_df['date'].max().strftime('%Y-%m')}"
            )

    # Priority 2: tab_df_long
    elif tab_df_long is not None and not tab_df_long.empty:
        data_ctx   = build_tab_specific_ai_context(tab_df_long, tab_product_type)
        ctx_source = "נתוני טאב פעיל (df_long)"
        ctx_rows   = len(tab_df_long)
        if "manager" in tab_df_long.columns:
            ctx_mgrs = sorted(tab_df_long["manager"].dropna().unique().tolist())

    # Priority 3: ISA-sheet summary
    else:
        ctx_key = "isa_chat_data_ctx"
        if ctx_key not in st.session_state or not full_df.empty:
            try:
                from institutional_strategy_analysis.ai_analyst import build_data_context_summary
                st.session_state[ctx_key] = build_data_context_summary(full_df)
            except Exception:
                st.session_state[ctx_key] = ""
        data_ctx = st.session_state.get(ctx_key, "")
        ctx_source = "ISA sheet (fallback)"

    # ── Debug expander ─────────────────────────────────────────────────────
    with st.expander("🔍 מקור הקשר AI", expanded=False):
        st.caption(
            f"**מקור:** {ctx_source}  \n"
            f"**סוג מוצר:** {tab_product_type or '—'}  \n"
            f"**גופים:** {', '.join(ctx_mgrs) if ctx_mgrs else '—'}  \n"
            f"**מסלולים:** {', '.join(ctx_tracks) if ctx_tracks else '—'}  \n"
            f"**רכיבים:** {', '.join(ctx_allocs) if ctx_allocs else '—'}  \n"
            f"**טווח תאריכים:** {ctx_range}  \n"
            f"**שורות:** {ctx_rows:,}"
        )

    history = st.session_state.get("isa_chat_history", [])

    # Render chat history
    for msg in history:
        role = msg["role"]
        with st.chat_message("user" if role == "user" else "assistant"):
            st.markdown(msg["content"])

    # Input box
    user_input = st.chat_input(
        "שאל שאלה על הנתונים... למשל: 'מי הגוף עם החשיפה הגבוהה ביותר לחו\"ל?'"
    )

    if user_input:
        # Show user message immediately
        with st.chat_message("user"):
            st.markdown(user_input)

        # Call AI
        with st.chat_message("assistant"):
            with st.spinner("AI מעבד..."):
                try:
                    from institutional_strategy_analysis.ai_analyst import run_chat_turn
                    reply, err = run_chat_turn(user_input, history, data_ctx)
                except Exception as e:
                    reply, err = "", str(e)

            if err:
                st.error(f"⚠️ {err}")
                reply = ""
            else:
                st.markdown(reply)

        # Append to history
        if reply or err:
            history.append({"role": "user",      "content": user_input})
            if reply:
                history.append({"role": "assistant", "content": reply})
            st.session_state["isa_chat_history"] = history[-20:]

    # Clear button
    if history:
        if st.button("🗑️ נקה שיחה", key="isa_chat_clear", use_container_width=False):
            st.session_state["isa_chat_history"] = []
            st.rerun()


# ── Main entry point ──────────────────────────────────────────────────────────

def render_institutional_analysis(
    product_type=None,
    df_long=None,
    selected_managers=None,
    expanded=False,
    use_expander=True,
):
    """Render the full "ניתוח אסטרטגיות מוסדיים" section.

    Parameters (all optional — backward compatible)
    ────────────────────────────────────────────────
    product_type      : str | None   – active product tab from parent app
    df_long           : pd.DataFrame | None – fund data from parent app
    selected_managers : list | None  – manager filter from session state
    """
    # Store received context in local working variables for future use
    _ctx_product_type      = product_type
    _ctx_df_long           = df_long
    _ctx_selected_managers = selected_managers

    # When called from the dedicated ISA research screen, skip the expander wrapper
    # (content renders directly). When embedded in the main optimizer, use expander.
    import contextlib as _cl

    @_cl.contextmanager
    def _maybe_expander():
        if use_expander:
            with st.expander("📐 ניתוח אסטרטגיות מוסדיים", expanded=expanded):
                yield
        else:
            yield

    with _maybe_expander():

        # ── Debug: show received context when available ───────────────────
        # (hidden from user — internal context only)
        pass  # _ctx_product_type, _ctx_df_long available for internal use if needed

        # ── Load data ─────────────────────────────────────────────────────
        with st.spinner("טוען נתונים..."):
            try:
                df_yearly, df_monthly, debug_info, errors = _load_data()
            except Exception as e:
                st.error(f"שגיאת טעינה: {e}")
                return

        if df_yearly.empty and df_monthly.empty:
            st.error("לא נטענו נתונים. בדוק את קישור הגיליון ואת הרשאות הגישה.")
            for e in errors:
                st.warning(e)
            return

        _render_debug(df_yearly, df_monthly, debug_info, errors)  # kept for developer use; hidden in UI by function guard below

        # ── Available options ─────────────────────────────────────────────
        opts = _options(df_yearly, df_monthly)

        # ── Build full manager universe before any UI filter ───────────────
        # Start with managers already in the ISA-sheet data (opts already normalized)
        from institutional_strategy_analysis.normalizer import normalize_manager_name
        isa_managers = set(opts["managers"])

        # Also pull managers from the parent-app df_long (active product/tab)
        tab_managers_raw:  list = []
        tab_managers_norm: dict = {}   # raw → (canonical, match_type)
        if _ctx_df_long is not None and not _ctx_df_long.empty and "manager" in _ctx_df_long.columns:
            for raw_mgr in _ctx_df_long["manager"].dropna().unique():
                canonical, match_type = normalize_manager_name(str(raw_mgr))
                tab_managers_raw.append(str(raw_mgr))
                tab_managers_norm[str(raw_mgr)] = (canonical, match_type)

        # Combine: ISA managers + normalized tab managers
        extra_canonical = {v[0] for v in tab_managers_norm.values()}
        full_manager_universe = sorted(isa_managers | extra_canonical)

        # Unresolved names from tab (for debug)
        unresolved = [r for r, (c, t) in tab_managers_norm.items() if t == "unresolved"]

        # Debug expander for managers — hidden from users
        # (unresolved / tab_managers_norm data kept in memory for internal use)

        # ── Filters ───────────────────────────────────────────────────────
        st.markdown("#### 🎛️ סינון")
        fc1, fc2, fc3 = st.columns(3)

        preferred_mgrs = [m for m in ["הראל", "מגדל"] if m in full_manager_universe]
        default_mgrs = preferred_mgrs or full_manager_universe[:min(2, len(full_manager_universe))]

        with fc1:
            sel_mgr = st.multiselect(
                "מנהל השקעות",
                options=full_manager_universe,
                default=default_mgrs,
                help="בחר גוף מוסדי אחד או יותר. הנתונים מציגים את אסטרטגיית האלוקציה שלהם לאורך זמן.",
                key="isa_managers",
            )
        with fc2:
            avail_tracks = sorted({
                t for df in (df_yearly, df_monthly) if not df.empty
                for t in df[df["manager"].isin(sel_mgr)]["track"].unique()
            }) if sel_mgr else opts["tracks"]
            default_tracks = [t for t in ["כללי"] if t in avail_tracks] or (avail_tracks[:1] if avail_tracks else [])
            sel_tracks = st.multiselect(
                "מסלול",
                options=avail_tracks,
                default=default_tracks,
                help="בחר מסלול השקעה — כגון כללי, מנייתי. מסלול כללי מאזן בין כמה נכסים.",
                key="isa_tracks",
            )
        with fc3:
            avail_allocs = sorted({
                a for df in (df_yearly, df_monthly) if not df.empty
                for a in df[
                    df["manager"].isin(sel_mgr) & df["track"].isin(sel_tracks)
                ]["allocation_name"].unique()
            }) if sel_mgr and sel_tracks else opts["allocation_names"]
            default_allocs = [a for a in avail_allocs if a == 'חו"ל']
            if not default_allocs:
                default_allocs = [a for a in avail_allocs if "חו" in a or "חול" in a][:1]
            if not default_allocs:
                default_allocs = avail_allocs[:1] if avail_allocs else []
            sel_allocs = st.multiselect(
                "רכיב אלוקציה",
                options=avail_allocs,
                default=default_allocs,
                help='בחר רכיבי חשיפה — למשל מניות, חו"ל, מט"ח, לא-סחיר.',
                key="isa_allocs",
            )

        # Time range — locked to "הכל" (other options removed from UI)
        sel_range = "הכל"
        custom_start = None

        if not sel_mgr or not sel_tracks or not sel_allocs:
            st.info("יש לבחור לפחות מנהל, מסלול ורכיב אחד.")
            return

        # ── Build display series ──────────────────────────────────────────
        filters = {"managers": sel_mgr, "tracks": sel_tracks,
                   "allocation_names": sel_allocs}

        display_df = _build_series(df_yearly, df_monthly, sel_range, custom_start, filters)

        if display_df.empty:
            st.warning("אין נתונים לסינון הנוכחי.")
            return

        # Quick stats row
        n_dates  = display_df["date"].nunique()
        n_yearly = (display_df["frequency"] == "yearly").sum()  if "frequency" in display_df.columns else 0
        n_monthly = (display_df["frequency"] == "monthly").sum() if "frequency" in display_df.columns else 0
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("נקודות זמן", n_dates)
        sc2.metric("נתונים חודשיים", n_monthly // max(1, display_df["allocation_name"].nunique()))
        sc3.metric("נתונים שנתיים",  n_yearly  // max(1, display_df["allocation_name"].nunique()))

        # ── Tabs ──────────────────────────────────────────────────────────
        t_ts, t_snap, t_delta, t_heat, t_stats, t_rank = st.tabs([
            "📈 סדרת זמן",
            "📍 Snapshot",
            "🔄 שינוי / Delta",
            "🌡️ Heatmap",
            "📊 סטטיסטיקות",
            "🏆 דירוג",
        ])

        # ── Tab 1: Time series ────────────────────────────────────────────
        with t_ts:
            from institutional_strategy_analysis.charts import build_timeseries
            fig = build_timeseries(display_df)
            _safe_plotly(fig, key="isa_ts")
            st.caption(
                "קווים מלאים = נתונים חודשיים | קווים מקווקוים = נתונים שנתיים. "
                "שנים שמכוסות על ידי נתונים חודשיים לא מוצגות כשנתיות."
            )
            col_dl, _ = st.columns([1, 5])
            with col_dl:
                st.download_button("⬇️ CSV", data=_csv(display_df),
                                   file_name="isa_timeseries.csv", mime="text/csv",
                                   key="isa_dl_ts")

        # ── Tab 2: Snapshot ───────────────────────────────────────────────
        with t_snap:
            max_d = display_df["date"].max().date()
            min_d = display_df["date"].min().date()
            snap_date = st.date_input(
                "תאריך Snapshot",
                value=max_d, min_value=min_d, max_value=max_d,
                help="מציג את הערך האחרון הידוע עד לתאריך שנבחר.",
                key="isa_snap_date",
            )
            from institutional_strategy_analysis.charts import build_snapshot
            _safe_plotly(build_snapshot(display_df, pd.Timestamp(snap_date)), key="isa_snap")

            snap_df = display_df[display_df["date"] <= pd.Timestamp(snap_date)]
            if not snap_df.empty:
                i = snap_df.groupby(["manager", "track", "allocation_name"])["date"].idxmax()
                tbl = snap_df.loc[i][["manager", "track", "allocation_name",
                                       "allocation_value", "date"]].copy()
                tbl["date"] = tbl["date"].dt.strftime("%Y-%m")
                tbl.columns = ["מנהל", "מסלול", "רכיב", "ערך (%)", "תאריך"]
                st.dataframe(tbl.sort_values("ערך (%)", ascending=False)
                               .reset_index(drop=True),
                             use_container_width=True, hide_index=True)

        # ── Tab 3: Delta ──────────────────────────────────────────────────
        with t_delta:
            min_d = display_df["date"].min().date()
            max_d = display_df["date"].max().date()
            dc1, dc2 = st.columns(2)
            with dc1:
                date_a = st.date_input("תאריך A (מוצא)",
                                       value=_clamp(max_d - timedelta(days=365), min_d, max_d),
                                       min_value=min_d, max_value=max_d,
                                       help="תאריך ההתחלה להשוואה.",
                                       key="isa_da")
            with dc2:
                date_b = st.date_input("תאריך B (יעד)", value=max_d,
                                       min_value=min_d, max_value=max_d,
                                       help="תאריך הסיום להשוואה.",
                                       key="isa_db")
            if date_a >= date_b:
                st.warning("תאריך A חייב להיות לפני B.")
            else:
                from institutional_strategy_analysis.charts import build_delta
                fig_d, delta_tbl = build_delta(display_df,
                                                pd.Timestamp(date_a),
                                                pd.Timestamp(date_b))
                _safe_plotly(fig_d, key="isa_delta")
                if not delta_tbl.empty:
                    st.dataframe(delta_tbl.reset_index(drop=True),
                                 use_container_width=True, hide_index=True)
                    col_dl2, _ = st.columns([1, 5])
                    with col_dl2:
                        st.download_button("⬇️ CSV", data=_csv(delta_tbl),
                                           file_name="isa_delta.csv", mime="text/csv",
                                           key="isa_dl_delta")

        # ── Tab 4: Heatmap ────────────────────────────────────────────────
        with t_heat:
            from institutional_strategy_analysis.charts import build_heatmap
            heat_df = display_df.copy()
            if display_df["date"].nunique() > 48:
                cutoff = display_df["date"].max() - pd.DateOffset(months=48)
                heat_df = display_df[display_df["date"] >= cutoff]
                st.caption("מוצגים 48 חודשים אחרונים. בחר 'הכל' לצפייה מלאה.")
            _safe_plotly(build_heatmap(heat_df), key="isa_heat")

        # ── Tab 5: Summary stats ──────────────────────────────────────────
        with t_stats:
            from institutional_strategy_analysis.charts import build_summary_stats
            stats = build_summary_stats(display_df)
            if stats.empty:
                st.info("אין מספיק נתונים לסטטיסטיקה.")
            else:
                st.dataframe(stats.reset_index(drop=True),
                             use_container_width=True, hide_index=True)
                col_dl3, _ = st.columns([1, 5])
                with col_dl3:
                    st.download_button("⬇️ CSV", data=_csv(stats),
                                       file_name="isa_stats.csv", mime="text/csv",
                                       key="isa_dl_stats")

        # ── Tab 6: Ranking ────────────────────────────────────────────────
        with t_rank:
            from institutional_strategy_analysis.charts import build_ranking
            if display_df["allocation_name"].nunique() > 1:
                rank_alloc = st.selectbox(
                    "רכיב לדירוג",
                    options=sorted(display_df["allocation_name"].unique()),
                    help="בחר רכיב שלפיו יוצג הדירוג החודשי.",
                    key="isa_rank_alloc",
                )
                rank_df = display_df[display_df["allocation_name"] == rank_alloc]
            else:
                rank_df = display_df

            _safe_plotly(
                build_ranking(rank_df,
                              title=f"דירוג מנהלים — {rank_df['allocation_name'].iloc[0]}"
                              if not rank_df.empty else "דירוג"),
                key="isa_rank",
            )

            # Volatility table
            if not rank_df.empty:
                vol = []
                for (mgr, trk), g in rank_df.groupby(["manager", "track"]):
                    chg = g.sort_values("date")["allocation_value"].diff().dropna()
                    vol.append({
                        "מנהל": mgr, "מסלול": trk,
                        "תנודתיות (STD)": round(chg.std(), 3) if len(chg) > 1 else float("nan"),
                        "שינוי מקסימלי": round(chg.abs().max(), 3) if not chg.empty else float("nan"),
                    })
                if vol:
                    st.caption("תנודתיות לפי מנהל:")
                    st.dataframe(
                        pd.DataFrame(vol).sort_values("תנודתיות (STD)", ascending=False)
                          .reset_index(drop=True),
                        use_container_width=True, hide_index=True,
                    )

        # ── Raw data ──────────────────────────────────────────────────────
        with st.expander("📋 נתונים גולמיים", expanded=False):
            disp = display_df.copy()
            if "date" in disp.columns:
                disp["date"] = disp["date"].dt.strftime("%Y-%m-%d")
            st.dataframe(disp.reset_index(drop=True),
                         use_container_width=True, hide_index=True)
            st.download_button("⬇️ ייצוא כל הנתונים", data=_csv(display_df),
                               file_name="isa_all.csv", mime="text/csv",
                               key="isa_dl_all")

        # ── AI Analysis — fully independent filters ───────────────────────
        _render_ai_section(
            df_yearly, df_monthly, opts,
            tab_df_long=_ctx_df_long,
            tab_product_type=_ctx_product_type,
        )
