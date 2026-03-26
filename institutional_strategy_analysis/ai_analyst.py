# -*- coding: utf-8 -*-
"""
institutional_strategy_analysis/ai_analyst.py
──────────────────────────────────────────────
Builds rich analytical prompts and calls Claude for deep institutional
investment strategy analysis at CIO / manager-selection level.

Public API
──────────
    run_ai_analysis(display_df, context)                          -> AnalysisResult
    run_focused_analysis(full_df, manager, track, peers, context) -> AnalysisResult
    run_comparison_analysis(df, mgr_a, trk_a, mgr_b, trk_b, ctx) -> AnalysisResult
    compute_manager_scorecard(full_df, manager, track)            -> list[dict]
"""
from __future__ import annotations

import os
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)


ISA_GUIDANCE_DOC_URL = "https://docs.google.com/document/d/1Hqh9TI2u7QRbTvRAS0TRkyL-28-eLIznkQbGTd_M1Wk/edit?usp=sharing"


def _extract_google_doc_id(url: str) -> str:
    m = re.search(r"/document/d/([^/]+)", url or "")
    return m.group(1) if m else ""


def _fetch_external_guidance(doc_url: str = ISA_GUIDANCE_DOC_URL) -> str:
    """Fetch AI writing instructions + supplementary manager info from Google Docs."""
    doc_id = _extract_google_doc_id(doc_url)
    if not doc_id:
        return ""

    export_urls = [
        f"https://docs.google.com/document/d/{doc_id}/export?format=txt",
        f"https://docs.google.com/document/u/0/d/{doc_id}/export?format=txt",
    ]

    headers = {"User-Agent": "Mozilla/5.0"}
    for url in export_urls:
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code == 200:
                txt = resp.text.strip()
                if txt and "JavaScript" not in txt[:300]:
                    return txt
        except Exception:
            continue
    return ""


def _external_guidance_block() -> str:
    guidance = _fetch_external_guidance()
    if guidance:
        return (
            "הנחיות כתיבה ומידע חיצוני נוסף על הגופים נמשכו כעת ממסמך Google Docs ייעודי.\n"
            "השתמש בהן כהנחיה המרכזית לניסוח הסקירה וכמידע משלים על כל גוף,\n"
            "בתנאי שאינן סותרות את הנתונים המספריים שקיבלת מהאפליקציה.\n\n"
            f"{guidance}"
        )
    return (
        "לא נטענו כרגע הנחיות הכתיבה והמידע החיצוני ממסמך Google Docs. "
        "במקרה כזה היצמד לנתונים שבאפליקציה בלבד, הימנע מהמצאת מידע חיצוני, "
        "ואל תסיק מעבר למה שנתמך בנתונים."
    )


# ── API key resolution (OpenAI — key set in Streamlit Secrets) ───────────────

def _get_api_key() -> str:
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "OPENAI_API_KEY" in st.secrets:
            return str(st.secrets["OPENAI_API_KEY"])
    except Exception:
        pass
    return os.getenv("OPENAI_API_KEY", "")


def _call_claude(prompt: str, system: str = "", max_tokens: int = 3200,
                 model: str = "gpt-4o") -> tuple[str, Optional[str]]:
    """Calls OpenAI Chat Completions. Name kept for internal compatibility."""
    api_key = _get_api_key()
    if not api_key:
        return "", "לא הוגדר מפתח OPENAI_API_KEY ב-Streamlit Secrets."

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"model": model, "max_tokens": max_tokens, "messages": messages},
            timeout=90,
        )
        if resp.status_code == 200:
            text = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return (text, None) if text else ("", "תגובה ריקה מהמודל.")
        elif resp.status_code == 401:
            return "", "מפתח OPENAI_API_KEY לא תקין."
        elif resp.status_code == 429:
            return "", "חריגה ממגבלת קצב בקשות. נסה שוב עוד כמה שניות."
        else:
            return "", f"שגיאת API: HTTP {resp.status_code}"
    except requests.exceptions.Timeout:
        return "", "תם הזמן הקצוב (90 שניות). נסה שוב."
    except Exception as e:
        return "", f"שגיאת תקשורת: {e}"


# ── Statistical computation ───────────────────────────────────────────────────

def _compute_rich_stats(df: pd.DataFrame, alloc: str, manager: str, track: str) -> dict:
    sub = df[
        (df["allocation_name"] == alloc) &
        (df["manager"] == manager) &
        (df["track"] == track)
    ].sort_values("date")

    if sub.empty or len(sub) < 2:
        return {}

    vals = sub["allocation_value"].dropna()
    if len(vals) < 2:
        return {}

    if "frequency" in sub.columns:
        m_sub = sub[sub["frequency"] == "monthly"]
        monthly_vals = m_sub["allocation_value"].dropna() if not m_sub.empty else vals
    else:
        monthly_vals = vals

    diffs = monthly_vals.diff().dropna()

    slope = 0.0
    if len(monthly_vals) >= 3:
        x = np.arange(len(monthly_vals))
        slope = float(np.polyfit(x, monthly_vals.values, 1)[0])

    reversals = 0
    if len(diffs) >= 2:
        signs = np.sign(diffs.values)
        reversals = int(np.sum(np.diff(signs) != 0))

    dynamism = float(diffs.abs().mean()) if not diffs.empty else 0.0

    max_date = sub["date"].max()

    yr_ago_df  = sub[sub["date"] <= max_date - pd.DateOffset(months=12)]
    yr_ago_val = float(yr_ago_df["allocation_value"].iloc[-1]) if not yr_ago_df.empty else float("nan")
    change_12m = round(float(vals.iloc[-1]) - yr_ago_val, 2) if not np.isnan(yr_ago_val) else float("nan")

    mo3_ago_df = sub[sub["date"] <= max_date - pd.DateOffset(months=3)]
    mo3_val    = float(mo3_ago_df["allocation_value"].iloc[-1]) if not mo3_ago_df.empty else float("nan")
    change_3m  = round(float(vals.iloc[-1]) - mo3_val, 2) if not np.isnan(mo3_val) else float("nan")

    recent_direction = "—"
    if len(diffs) >= 3:
        last3 = diffs.iloc[-3:].mean()
        if last3 > 0.3:    recent_direction = "עולה"
        elif last3 < -0.3: recent_direction = "יורדת"
        else:              recent_direction = "יציבה"

    return {
        "current":          round(float(vals.iloc[-1]), 2),
        "mean":             round(float(vals.mean()), 2),
        "min":              round(float(vals.min()), 2),
        "max":              round(float(vals.max()), 2),
        "std":              round(float(vals.std()), 2),
        "range_pp":         round(float(vals.max() - vals.min()), 2),
        "slope_monthly":    round(slope, 3),
        "dynamism":         round(dynamism, 3),
        "reversals":        reversals,
        "change_12m":       change_12m,
        "change_3m":        change_3m,
        "recent_direction": recent_direction,
        "mom_avg":          round(float(diffs.mean()), 3) if not diffs.empty else 0,
        "mom_max":          round(float(diffs.abs().max()), 3) if not diffs.empty else 0,
        "n_monthly":        int((sub["frequency"] == "monthly").sum()) if "frequency" in sub.columns else 0,
        "n_yearly":         int((sub["frequency"] == "yearly").sum()) if "frequency" in sub.columns else 0,
        "date_first":       sub["date"].min().strftime("%Y-%m"),
        "date_last":        sub["date"].max().strftime("%Y-%m"),
    }


def _compute_manager_profile(df: pd.DataFrame, manager: str, track: str) -> dict:
    sub = df[(df["manager"] == manager) & (df["track"] == track)]
    if sub.empty:
        return {}

    allocs    = sub["allocation_name"].unique()
    per_alloc = {a: _compute_rich_stats(df, a, manager, track) for a in allocs}
    per_alloc = {k: v for k, v in per_alloc.items() if v}

    fx_key  = next((k for k in allocs if any(x in k for x in ['מט"ח', 'מטח', 'fx', 'FX', 'currency'])), None)
    fgn_key = next((k for k in allocs if any(x in k for x in ['חו"ל', 'חול', 'foreign', 'Foreign'])), None)
    eq_key  = next((k for k in allocs if any(x in k for x in ['מניות', 'מנייתי', 'equity', 'Equity'])), None)

    hedging_ratio = None
    if fx_key and fgn_key:
        fx_now  = per_alloc.get(fx_key, {}).get("current")
        fgn_now = per_alloc.get(fgn_key, {}).get("current")
        if fx_now is not None and fgn_now and fgn_now > 0:
            hedging_ratio = round(fx_now / fgn_now * 100, 1)

    dyn_vals         = [v["dynamism"] for v in per_alloc.values() if "dynamism" in v]
    overall_dynamism = round(float(np.mean(dyn_vals)), 3) if dyn_vals else 0.0
    total_reversals  = sum(v.get("reversals", 0) for v in per_alloc.values())

    risk_trend = None
    if eq_key and eq_key in per_alloc:
        s = per_alloc[eq_key].get("slope_monthly", 0)
        if s > 0.3:    risk_trend = "מגדיל סיכון (מניות עולות)"
        elif s < -0.3: risk_trend = "מקטין סיכון (מניות יורדות)"
        else:          risk_trend = "יציב"

    return {
        "per_alloc":        per_alloc,
        "hedging_ratio":    hedging_ratio,
        "overall_dynamism": overall_dynamism,
        "total_reversals":  total_reversals,
        "risk_trend":       risk_trend,
        "fx_key":           fx_key,
        "fgn_key":          fgn_key,
        "eq_key":           eq_key,
    }


def _cross_manager_snapshot(df: pd.DataFrame, alloc: str) -> str:
    sub = df[df["allocation_name"] == alloc].copy()
    if sub.empty:
        return "  (אין נתונים)"
    idx  = sub.groupby(["manager", "track"])["date"].idxmax()
    snap = sub.loc[idx].sort_values("allocation_value", ascending=False)
    return "\n".join(
        f"  {row['manager']} [{row['track']}]: {row['allocation_value']:.1f}%"
        for _, row in snap.iterrows()
    )


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM = (
    "אתה מנתח השקעות מוסדיות בעברית. "
    "היצמד לנתונים המספריים שנמסרו לך ולהנחיות החיצוניות שצורפו מהמסמך. "
    "אל תמציא נתונים, ואל תציג מידע חיצוני כעובדה אם אינו נתמך בהקשר שקיבלת."
)


# ── Prompt: Market-wide analysis (all selected managers) ─────────────────────

def _build_full_prompt(display_df: pd.DataFrame, context: dict) -> str:
    managers         = context.get("managers", [])
    tracks           = context.get("tracks", [])
    allocation_names = context.get("allocation_names", [])
    sel_range        = context.get("selected_range", "הכל")
    stats_summary    = context.get("stats_summary", "")

    blocks         = []
    all_stats_flat = []

    for mgr in managers:
        for trk in tracks:
            profile = _compute_manager_profile(display_df, mgr, trk)
            if not profile or not profile["per_alloc"]:
                continue

            lines = ["", "=" * 54, f"גוף: {mgr} | מסלול: {trk}", "-" * 54]
            dyn = profile["overall_dynamism"]
            dyn_label = "גבוהה" if dyn > 1.0 else "בינונית" if dyn > 0.4 else "נמוכה"
            lines.append(f"  דינמיות כוללת: {dyn:.3f} pp/ח ({dyn_label})")
            lines.append(f"  שינויי כיוון:  {profile['total_reversals']}")
            if profile["risk_trend"]:
                lines.append(f"  מגמת סיכון:    {profile['risk_trend']}")
            if profile["hedging_ratio"] is not None:
                hr = profile["hedging_ratio"]
                hr_lbl = "מגדר מלא" if hr > 80 else "מגדר חלקי" if hr > 40 else "חשוף מטח"
                lines.append(f'  גידור מטח/חול: {hr:.0f}% ({hr_lbl})')
            lines.append("  רכיבים:")

            for alloc, s in profile["per_alloc"].items():
                c12 = f"{s['change_12m']:+.1f}pp" if not np.isnan(s.get("change_12m", float("nan"))) else "—"
                c3  = f"{s.get('change_3m', float('nan')):+.1f}pp" if not np.isnan(s.get("change_3m", float("nan"))) else "—"
                lines.append(
                    f"    {alloc}: נוכחי={s['current']}% ממוצע={s['mean']}% "
                    f"σ={s['std']}pp מגמה={s['slope_monthly']:+.3f}pp/ח "
                    f"12ח={c12} 3ח={c3} כיוון={s.get('recent_direction','—')} "
                    f"דינמיות={s['dynamism']:.3f}"
                )
                all_stats_flat.append({**s, "manager": mgr, "track": trk, "alloc": alloc})
            blocks.append("\n".join(lines))

    cross_lines = ["\nהשוואה נוכחית בין גופים (ממויין יורד):"]
    for alloc in allocation_names:
        cross_lines.append(f"\n{alloc}:\n{_cross_manager_snapshot(display_df, alloc)}")

    risk_lines = []
    for s in all_stats_flat:
        if "סחיר" in s["alloc"] and s["current"] > 30:
            risk_lines.append(f"  חשיפה גבוהה ללא-סחיר: {s['manager']} [{s['track']}] {s['current']}%")
        if s.get("std", 0) > 5:
            risk_lines.append(f"  תנודתיות גבוהה: {s['manager']} [{s['track']}] {s['alloc']} σ={s['std']}pp")
        if s.get("slope_monthly", 0) < -0.5:
            risk_lines.append(f"  ירידה חדה: {s['manager']} [{s['track']}] {s['alloc']} {s['slope_monthly']:+.2f}pp/ח")
        if s.get("slope_monthly", 0) > 0.5:
            risk_lines.append(f"  עלייה חדה: {s['manager']} [{s['track']}] {s['alloc']} {s['slope_monthly']:+.2f}pp/ח")

    data_block    = "\n".join(blocks) or "(אין נתונים)"
    cross_section = "\n".join(cross_lines)
    risk_section  = "\n".join(risk_lines) if risk_lines else "  לא זוהו חריגות."
    stats_block   = f"\nסטטיסטיקות:\n{stats_summary}" if stats_summary else ""

    return f"""ניתוח שוק — אסטרטגיות מוסדיים. טווח: {sel_range}.
pp = נקודות אחוז | ח = חודש | σ = סטיית תקן | דינמיות = ΔΔ חודשי ממוצע.

{data_block}

{cross_section}

אותות סיכון וחריגה:
{risk_section}
{stats_block}

---
הנחיות ומידע חיצוני ממסמך Google Docs:
{_external_guidance_block()}

כתוב את הניתוח לפי ההנחיות החיצוניות שנטענו מהמסמך. אם יש סתירה בין המסמך לבין הנתונים המספריים שבאפליקציה — הנתונים המספריים קודמים."""


# ── Prompt: Focused single-manager analysis vs peer group ────────────────────

def _build_focused_prompt(
    full_df: pd.DataFrame,
    manager: str,
    track: str,
    peer_managers: list,
    context: dict,
) -> str:
    focus_profile = _compute_manager_profile(full_df, manager, track)
    if not focus_profile or not focus_profile["per_alloc"]:
        return ""

    all_in_track = full_df[full_df["track"] == track]["manager"].unique().tolist()
    if peer_managers:
        peers = [m for m in peer_managers if m != manager and m in all_in_track]
    else:
        peers = [m for m in all_in_track if m != manager]
    if not peers:
        return ""

    peer_profiles = {pm: _compute_manager_profile(full_df, pm, track) for pm in peers}
    peer_profiles = {pm: pp for pm, pp in peer_profiles.items() if pp}

    alloc_blocks = []
    for alloc, fs in focus_profile["per_alloc"].items():
        peer_data = []
        for pm, pp in peer_profiles.items():
            ps = pp["per_alloc"].get(alloc)
            if ps:
                peer_data.append({"manager": pm, **ps})
        if not peer_data:
            continue

        p_curr  = [p["current"]       for p in peer_data]
        p_slope = [p["slope_monthly"] for p in peer_data]
        p_dyn   = [p["dynamism"]      for p in peer_data]
        p_std   = [p["std"]           for p in peer_data]
        p_c12   = [p["change_12m"]    for p in peer_data if not np.isnan(p.get("change_12m", float("nan")))]
        p_c3    = [p.get("change_3m", float("nan")) for p in peer_data if not np.isnan(p.get("change_3m", float("nan")))]

        peer_mean   = round(float(np.mean(p_curr)), 2)
        peer_median = round(float(np.median(p_curr)), 2)
        peer_min_v  = round(float(np.min(p_curr)), 2)
        peer_max_v  = round(float(np.max(p_curr)), 2)
        peer_xstd   = round(float(np.std(p_curr)), 2)

        diff_mean   = round(fs["current"] - peer_mean, 2)
        diff_median = round(fs["current"] - peer_median, 2)

        ranking = sorted(
            [(manager, fs["current"])] + [(p["manager"], p["current"]) for p in peer_data],
            key=lambda x: -x[1],
        )
        rank    = next((i + 1 for i, (m, _) in enumerate(ranking) if m == manager), None)
        n_total = len(ranking)
        rank_str = " | ".join(f"{i+1}.{m}:{v:.1f}%" for i, (m, v) in enumerate(ranking))

        c12s = f"{fs['change_12m']:+.2f}pp"            if not np.isnan(fs.get("change_12m", float("nan"))) else "—"
        c3s  = f"{fs.get('change_3m', float('nan')):+.2f}pp" if not np.isnan(fs.get("change_3m", float("nan"))) else "—"
        pc12 = f"{np.mean(p_c12):+.2f}pp" if p_c12 else "—"
        pc3  = f"{np.mean(p_c3):+.2f}pp"  if p_c3  else "—"

        blk = (
            f"\n{'─'*58}\n"
            f"▶ {alloc}\n"
            f"{'─'*58}\n"
            f"  נוכחי:       {manager}={fs['current']}%  |  "
            f"עמיתים: ממוצע={peer_mean}%, מדיאן={peer_median}%, "
            f"טווח={peer_min_v}–{peer_max_v}%, σ_בין-גופי={peer_xstd}pp\n"
            f"  פרמיה/דיסק:  vs ממוצע {diff_mean:+.2f}pp  |  vs מדיאן {diff_median:+.2f}pp\n"
            f"  דירוג:       {rank}/{n_total}  (1=הגבוה ביותר)\n"
            f"  מגמה:        {manager} {fs['slope_monthly']:+.3f}pp/ח  |  עמיתים {np.mean(p_slope):+.3f}pp/ח\n"
            f"  שינוי 12ח:   {manager} {c12s}  |  עמיתים {pc12}\n"
            f"  שינוי 3ח:    {manager} {c3s}   |  עמיתים {pc3}\n"
            f"  כיוון אחרון: {fs.get('recent_direction','—')}\n"
            f"  תזזיתיות:    {manager} {fs['dynamism']:.3f}pp/ח  |  עמיתים {np.mean(p_dyn):.3f}pp/ח\n"
            f"  תנודתיות:    {manager} σ={fs['std']:.2f}pp  |  עמיתים σ_ממוצע={np.mean(p_std):.2f}pp\n"
            f"  היסטוריה:    ממוצע={fs['mean']}%, מינ={fs['min']}%, מקס={fs['max']}%, "
            f"טווח={fs['range_pp']}pp, σ={fs['std']:.2f}pp, שינויי-כיוון={fs['reversals']}\n"
            f"  דירוג מלא:   {rank_str}\n"
        )
        alloc_blocks.append(blk)

    data_block = "\n".join(alloc_blocks) or "(אין נתונים)"

    hist_lines = []
    for alloc, s in focus_profile["per_alloc"].items():
        drift = round(s["current"] - s["mean"], 2)
        hist_lines.append(
            f"  {alloc}: {s['date_first']}–{s['date_last']}  |  "
            f"ממוצע={s['mean']}%  נוכחי={s['current']}%  drift={drift:+.1f}pp  |  "
            f"מקס={s['max']}%  מינ={s['min']}%  |  σ={s['std']:.2f}pp  שינויי-כיוון={s['reversals']}"
        )
    history_block = "\n".join(hist_lines)

    dyn  = focus_profile.get("overall_dynamism", 0)
    rev  = focus_profile.get("total_reversals", 0)
    p_dov = [pp.get("overall_dynamism", 0) for pp in peer_profiles.values()]
    p_rev = [pp.get("total_reversals",  0) for pp in peer_profiles.values()]
    peer_dyn_avg = round(np.mean(p_dov), 3) if p_dov else 0
    peer_rev_avg = round(np.mean(p_rev), 1) if p_rev else 0

    dyn_verdict = (
        "תזזיתי יותר מהממוצע" if dyn > peer_dyn_avg * 1.2 else
        "יציב יותר מהממוצע"   if dyn < peer_dyn_avg * 0.8 else
        "דומה לממוצע הקבוצה"
    )

    style_block = (
        f"  דינמיות כוללת:   {dyn:.3f}pp/ח  |  עמיתים {peer_dyn_avg:.3f}pp/ח  →  {dyn_verdict}\n"
        f"  שינויי כיוון:    {rev}  |  עמיתים ממוצע {peer_rev_avg:.0f}\n"
        f"  מגמת סיכון:      {focus_profile.get('risk_trend', '—')}\n"
    )
    if focus_profile.get("hedging_ratio") is not None:
        p_hr = [pp["hedging_ratio"] for pp in peer_profiles.values() if pp.get("hedging_ratio") is not None]
        hr_peer = f"  |  עמיתים {np.mean(p_hr):.0f}%" if p_hr else ""
        style_block += f'  יחס גידור מט"ח/חו"ל: {focus_profile["hedging_ratio"]:.0f}%{hr_peer}\n'

    peers_str  = ", ".join(peers)
    date_range = f"{context.get('date_min', '?')} – {context.get('date_max', '?')}"

    return f"""ניתוח מיקוד מעמיק — {manager} | מסלול: {track}
קבוצת ייחוס (Peer Group): {peers_str}  (N={len(peers)})
טווח נתונים: {date_range} | {context.get('selected_range', 'הכל')}
pp = נקודות אחוז | 1=הגבוה בדירוג

{'='*60}
I. נתוני השוואה יחסית לפי רכיב אלוקציה
{'='*60}
{data_block}

{'='*60}
II. פרופיל היסטורי עצמי
{'='*60}
{history_block}

{'='*60}
III. אפיון סגנון ניהול
{'='*60}
{style_block}

{'='*60}
הנחיות ומידע חיצוני ממסמך Google Docs
{'='*60}
{_external_guidance_block()}

פעל לפי ההנחיות החיצוניות שנטענו מהמסמך, והסתמך על הנתונים המספריים שלמעלה כבסיס הראשי לכל קביעה.
• רמת הסיכון הכוללת לעומת הקבוצה — מבוסס נתונים.
• נקודות שימת לב: תנודתיות, חשיפה ללא-סחיר, שינויים חדים.
• האם הסיכון מוצדק ביחס לפרופיל המנהל?

## גזר דין — בחירת מנהל (Manager Selection Verdict)
• לאיזה פרופיל חוסך הגוף מתאים ביותר? (גיל, שנאת סיכון, אופק)
• מה ה-edge הייחודי של הגוף — מה הוא עושה טוב יותר?
• מה הסיכון/חסרון המרכזי לעומת החלופות?
• לאיזה תרחיש שוק הגוף מיצב עצמו (risk-on / risk-off / stagflation)?"""


# ── Prompt: Head-to-head comparison ──────────────────────────────────────────

def _build_comparison_prompt(
    display_df: pd.DataFrame,
    mgr_a: str, trk_a: str,
    mgr_b: str, trk_b: str,
) -> str:
    prof_a = _compute_manager_profile(display_df, mgr_a, trk_a)
    prof_b = _compute_manager_profile(display_df, mgr_b, trk_b)
    if not prof_a or not prof_b:
        return ""

    def _pt(mgr, trk, prof):
        lines = [f"גוף: {mgr} | מסלול: {trk}"]
        lines.append(f"  דינמיות: {prof['overall_dynamism']:.3f} pp/ח  |  שינויי כיוון: {prof['total_reversals']}")
        if prof.get("risk_trend"):
            lines.append(f"  מגמת סיכון: {prof['risk_trend']}")
        if prof.get("hedging_ratio") is not None:
            lines.append(f"  גידור מטח/חול: {prof['hedging_ratio']:.0f}%")
        for alloc, s in prof["per_alloc"].items():
            c12 = f"{s['change_12m']:+.1f}pp"                       if not np.isnan(s.get("change_12m", float("nan"))) else "—"
            c3  = f"{s.get('change_3m', float('nan')):+.1f}pp"      if not np.isnan(s.get("change_3m", float("nan"))) else "—"
            lines.append(
                f"    {alloc}: {s['current']}%  (ממוצע={s['mean']}%, σ={s['std']:.1f}pp, "
                f"מגמה={s['slope_monthly']:+.2f}pp/ח, 12ח={c12}, 3ח={c3}, "
                f"דינמיות={s['dynamism']:.3f}pp/ח)"
            )
        return "\n".join(lines)

    shared = sorted(set(prof_a["per_alloc"]) & set(prof_b["per_alloc"]))
    diffs  = []
    for alloc in shared:
        sa = prof_a["per_alloc"][alloc]
        sb = prof_b["per_alloc"][alloc]
        d  = sa["current"] - sb["current"]
        dyn_w = mgr_a if sa["dynamism"] > sb["dynamism"] else mgr_b
        diffs.append(
            f"  {alloc}: {mgr_a}={sa['current']}% vs {mgr_b}={sb['current']}%  "
            f"(הפרש {d:+.1f}pp)  |  σ: {sa['std']:.1f} vs {sb['std']:.1f}  |  "
            f"תזזיתי יותר: {dyn_w}"
        )

    return f"""השוואה ישירה — ניתוח manager selection.
pp = נקודות אחוז.

{'='*58}
גוף A:
{_pt(mgr_a, trk_a, prof_a)}

{'='*58}
גוף B:
{_pt(mgr_b, trk_b, prof_b)}

{'='*58}
הפרשים ישירים לפי רכיב:
{chr(10).join(diffs) if diffs else "(אין רכיבים משותפים)"}

---
כתוב השוואה מקצועית — ברמת manager selection report —
עם הכותרות הבאות בדיוק (##):

## סיכום מנהלי (Executive Summary)
2–3 משפטים: מה ההבדל המהותי והאסטרטגי בין הגופים.
ציין: מי שמרני יותר, מי אגרסיבי יותר, מה ה-edge של כל אחד.

## השוואה יחסית לפי רכיב
לכל רכיב — חו"ל, מניות, מט"ח, לא-סחיר — בנפרד:
• מי גבוה יותר ובכמה pp, מה המשמעות
• האם ישנו הבדל מגמתי (אחד מגדיל, השני מקטין)?
• מה ההשלכה המעשית לחוסך?

## יתרונות {mgr_a} [{trk_a}] על פני {mgr_b} [{trk_b}]
לפחות 3 יתרונות קונקרטיים ומבוססי נתונים.

## יתרונות {mgr_b} [{trk_b}] על פני {mgr_a} [{trk_a}]
לפחות 3 יתרונות קונקרטיים ומבוססי נתונים.

## הבדלי סגנון ניהול (Management Style Delta)
• מי תזזיתי יותר ומה ההשלכות בתרחישי שוק שונים
• מי עקבי יותר — מה מסמל זאת לגבי ה-investment philosophy
• כיצד כל גוף מגיב לתנודתיות שוק?

## אסטרטגיית גידור (Hedging Comparison)
• מי חשוף יותר לסיכון מטבע ולמה?
• ההשלכה בתרחיש היחלשות שקל / DXY חזק.

## המלצה לפי פרופיל משקיע
גיל 25–45 (צבירה אגרסיבית):    מי עדיף ולמה?
גיל 45–60 (שימור והגנה):       מי עדיף ולמה?
שנאת סיכון גבוהה:              מי עדיף ולמה?
אי-ודאות גיאו-פוליטית:         מי מוגן יותר?
סביבת ריבית עולה:              מי מותאם יותר?"""


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    raw_text: str = ""
    sections: dict = field(default_factory=dict)
    error: Optional[str] = None

    def parse_sections(self):
        if not self.raw_text:
            return
        current_title = "כללי"
        current_lines: list = []
        for line in self.raw_text.splitlines():
            if line.startswith("## "):
                if current_lines:
                    self.sections[current_title] = "\n".join(current_lines).strip()
                current_title = line[3:].strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_lines:
            self.sections[current_title] = "\n".join(current_lines).strip()


# ── Public API ────────────────────────────────────────────────────────────────

def run_ai_analysis(display_df: pd.DataFrame, context: dict) -> AnalysisResult:
    if display_df.empty:
        return AnalysisResult(error="אין נתונים לניתוח.")
    prompt = _build_full_prompt(display_df, context)
    text, err = _call_claude(prompt, system=_SYSTEM, max_tokens=3200)
    result = AnalysisResult(raw_text=text, error=err)
    if text:
        result.parse_sections()
    return result


def run_focused_analysis(
    full_df: pd.DataFrame,
    manager: str,
    track: str,
    peer_managers,
    context: dict,
) -> AnalysisResult:
    if full_df.empty:
        return AnalysisResult(error="אין נתונים לניתוח.")
    prompt = _build_focused_prompt(full_df, manager, track, peer_managers, context)
    if not prompt:
        return AnalysisResult(error="לא נמצאו נתונים מספיקים לניתוח מיקוד.")
    text, err = _call_claude(prompt, system=_SYSTEM, max_tokens=3500)
    result = AnalysisResult(raw_text=text, error=err)
    if text:
        result.parse_sections()
    return result


def run_comparison_analysis(
    display_df: pd.DataFrame,
    mgr_a: str, trk_a: str,
    mgr_b: str, trk_b: str,
    context: dict,
) -> AnalysisResult:
    if display_df.empty:
        return AnalysisResult(error="אין נתונים לניתוח.")
    if mgr_a == mgr_b and trk_a == trk_b:
        return AnalysisResult(error="יש לבחור שני גופים/מסלולים שונים.")
    prompt = _build_comparison_prompt(display_df, mgr_a, trk_a, mgr_b, trk_b)
    if not prompt:
        return AnalysisResult(error="לא נמצאו נתונים לאחד מהגופים הנבחרים.")
    text, err = _call_claude(prompt, system=_SYSTEM, max_tokens=3200)
    result = AnalysisResult(raw_text=text, error=err)
    if text:
        result.parse_sections()
    return result


# ── Quick scorecard (no API call) ─────────────────────────────────────────────

def compute_manager_scorecard(full_df: pd.DataFrame, manager: str, track: str) -> list:
    """
    Returns per-allocation relative stats for the quick scorecard widget.
    No API call needed — pure statistics.
    """
    profile = _compute_manager_profile(full_df, manager, track)
    if not profile:
        return []

    all_managers = full_df[full_df["track"] == track]["manager"].unique().tolist()
    rows = []
    for alloc, fs in profile["per_alloc"].items():
        peer_vals = []
        for pm in all_managers:
            if pm == manager:
                continue
            ps = _compute_rich_stats(full_df, alloc, pm, track)
            if ps:
                peer_vals.append(ps["current"])

        if not peer_vals:
            continue

        peer_mean = round(float(np.mean(peer_vals)), 2)
        ranking   = sorted(
            [(manager, fs["current"])] + [(None, v) for v in peer_vals],
            key=lambda x: -x[1],
        )
        rank = next((i + 1 for i, (m, _) in enumerate(ranking) if m == manager), None)

        rows.append({
            "alloc":      alloc,
            "current":    fs["current"],
            "peer_mean":  peer_mean,
            "diff_mean":  round(fs["current"] - peer_mean, 2),
            "rank":       rank,
            "n_total":    len(ranking),
            "direction":  fs.get("recent_direction", "—"),
            "change_3m":  fs.get("change_3m", float("nan")),
            "change_12m": fs.get("change_12m", float("nan")),
            "dynamism":   fs.get("dynamism", 0),
        })
    return rows


# ── Open chat with AI about the data ─────────────────────────────────────────

_CHAT_SYSTEM = (
    "אתה אנליסט השקעות מוסדיות בכיר הדן בחופשיות עם מתכנן פיננסי. "
    "יש לך גישה לנתוני אלוקציה של גופים מוסדיים ישראלים (קרנות פנסיה, "
    "קרנות השתלמות, קופות גמל). ענה בעברית, בצורה תמציתית ומקצועית. "
    "כשרלוונטי — הסתמך על הנתונים שסופקו. אל תמציא נתונים שאינם בהקשר."
)


def run_chat_turn(
    user_message: str,
    history: list,
    data_context: str,
    model: str = "gpt-4o",
) -> tuple[str, Optional[str]]:
    """
    Send one chat turn to OpenAI.
    history = list of {"role": ..., "content": ...} dicts (prior turns).
    data_context = brief stats snapshot injected as system context.
    Returns (reply_text, error_or_None).
    """
    api_key = _get_api_key()
    if not api_key:
        return "", "לא הוגדר מפתח OPENAI_API_KEY ב-Streamlit Secrets."

    system_with_ctx = _CHAT_SYSTEM
    if data_context:
        system_with_ctx += (
            "\n\n--- נתוני הסשן הנוכחי ---\n" + data_context
        )

    messages = [{"role": "system", "content": system_with_ctx}]
    messages += history
    messages.append({"role": "user", "content": user_message})

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"model": model, "max_tokens": 1200, "messages": messages},
            timeout=60,
        )
        if resp.status_code == 200:
            text = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return (text, None) if text else ("", "תגובה ריקה.")
        elif resp.status_code == 401:
            return "", "מפתח OPENAI_API_KEY לא תקין."
        elif resp.status_code == 429:
            return "", "חריגה ממגבלת קצב. נסה שוב."
        else:
            return "", f"שגיאת API: HTTP {resp.status_code}"
    except requests.exceptions.Timeout:
        return "", "תם הזמן הקצוב. נסה שוב."
    except Exception as e:
        return "", f"שגיאת תקשורת: {e}"


def build_data_context_summary(full_df: pd.DataFrame) -> str:
    """
    Build a compact text snapshot of current data for the chat system prompt.
    """
    if full_df.empty:
        return "אין נתונים טעונים."
    lines = []
    managers = full_df["manager"].unique().tolist()
    tracks   = full_df["track"].unique().tolist()
    allocs   = full_df["allocation_name"].unique().tolist()
    date_min = full_df["date"].min().strftime("%Y-%m") if "date" in full_df.columns else "?"
    date_max = full_df["date"].max().strftime("%Y-%m") if "date" in full_df.columns else "?"
    lines.append(f"גופים: {', '.join(managers)}")
    lines.append(f"מסלולים: {', '.join(tracks)}")
    lines.append(f"רכיבי אלוקציה: {', '.join(allocs)}")
    lines.append(f"טווח נתונים: {date_min} – {date_max}")
    # Latest snapshot per manager/track/alloc
    snap_lines = []
    idx = full_df.groupby(["manager", "track", "allocation_name"])["date"].idxmax()
    snap = full_df.loc[idx]
    for _, row in snap.iterrows():
        snap_lines.append(
            f"  {row['manager']} [{row['track']}] {row['allocation_name']}: "
            f"{row['allocation_value']:.1f}%"
        )
    lines.append("ערכים עדכניים:\n" + "\n".join(snap_lines))
    return "\n".join(lines)
