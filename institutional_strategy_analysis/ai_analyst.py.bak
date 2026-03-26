# -*- coding: utf-8 -*-
"""
institutional_strategy_analysis/ai_analyst.py
──────────────────────────────────────────────
Builds rich prompts from display-series data and calls Claude for
deep institutional investment analysis.

Covers:
  • Per-manager narrative
  • Cross-manager comparison
  • Risk implications (volatility, drawdown, illiquid exposure)
  • Return proxy analysis (equity / foreign exposure as return driver)
  • Trend detection (momentum, reversals, inflection points)
  • Strategic interpretation (what positioning means for the investor)

Public API
──────────
    run_ai_analysis(display_df, context) -> AnalysisResult
    AnalysisResult.sections  -> dict[str, str]   (keyed analysis sections)
    AnalysisResult.error     -> str | None
"""
from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ── API helper ────────────────────────────────────────────────────────────────

def _get_api_key() -> str:
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "ANTHROPIC_API_KEY" in st.secrets:
            return str(st.secrets["ANTHROPIC_API_KEY"])
    except Exception:
        pass
    return os.getenv("ANTHROPIC_API_KEY", "")


def _call_claude(prompt: str, max_tokens: int = 900, model: str = "claude-sonnet-4-6") -> tuple[str, Optional[str]]:
    """
    Call Claude API.  Returns (text, error_or_None).
    Uses claude-sonnet-4-6 for richer analysis (vs haiku used elsewhere).
    """
    api_key = _get_api_key()
    if not api_key:
        return "", "מפתח ANTHROPIC_API_KEY לא מוגדר. הוסף אותו ב-Streamlit Secrets."

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=45,
        )
        if resp.status_code == 200:
            data = resp.json()
            for blk in data.get("content", []):
                if blk.get("type") == "text":
                    return blk["text"].strip(), None
            return "", "תגובה ריקה מהמודל."
        elif resp.status_code == 401:
            return "", "מפתח API לא תקין."
        elif resp.status_code == 429:
            return "", "חריגה ממגבלת קצב בקשות. נסה שוב עוד כמה שניות."
        else:
            return "", f"שגיאת API: HTTP {resp.status_code}"
    except requests.exceptions.Timeout:
        return "", "תם הזמן הקצוב לבקשה. נסה שוב."
    except Exception as e:
        return "", f"שגיאת תקשורת: {e}"


# ── Data summarisation helpers ────────────────────────────────────────────────

def _format_series_for_prompt(df: pd.DataFrame, alloc: str, manager: str, track: str) -> str:
    """Return a concise text table of date→value for one series."""
    sub = df[
        (df["allocation_name"] == alloc) &
        (df["manager"] == manager) &
        (df["track"] == track)
    ].sort_values("date")

    if sub.empty:
        return "  (אין נתונים)"

    lines = []
    for _, row in sub.iterrows():
        freq_tag = "(ש)" if row.get("frequency") == "yearly" else "(ח)"
        date_str = row["date"].strftime("%Y") if row.get("frequency") == "yearly" \
                   else row["date"].strftime("%m/%Y")
        lines.append(f"  {date_str}{freq_tag}: {row['allocation_value']:.1f}%")
    return "\n".join(lines)


def _compute_stats(df: pd.DataFrame, alloc: str, manager: str, track: str) -> dict:
    """Compute key stats for one series."""
    sub = df[
        (df["allocation_name"] == alloc) &
        (df["manager"] == manager) &
        (df["track"] == track)
    ].sort_values("date")

    if sub.empty or len(sub) < 2:
        return {}

    vals = sub["allocation_value"]
    monthly = sub[sub["frequency"] == "monthly"]["allocation_value"] if "frequency" in sub.columns else vals
    diffs = monthly.diff().dropna()

    # Trend: linear regression slope on monthly data
    if len(monthly) >= 3:
        x = np.arange(len(monthly))
        slope = float(np.polyfit(x, monthly.values, 1)[0])
    else:
        slope = 0.0

    # Max drawdown period
    peak = vals.cummax()
    drawdown = (vals - peak)
    max_dd = float(drawdown.min())

    return {
        "current":    round(float(vals.iloc[-1]), 2),
        "mean":       round(float(vals.mean()), 2),
        "min":        round(float(vals.min()), 2),
        "max":        round(float(vals.max()), 2),
        "std":        round(float(vals.std()), 2),
        "range_pp":   round(float(vals.max() - vals.min()), 2),
        "slope_monthly": round(slope, 3),   # pp per month
        "max_drawdown":  round(max_dd, 2),
        "mom_avg":    round(float(diffs.mean()), 2) if not diffs.empty else 0,
        "mom_max":    round(float(diffs.abs().max()), 2) if not diffs.empty else 0,
        "n_monthly":  int((sub["frequency"] == "monthly").sum()) if "frequency" in sub.columns else 0,
        "n_yearly":   int((sub["frequency"] == "yearly").sum()) if "frequency" in sub.columns else 0,
        "date_first": sub["date"].min().strftime("%Y-%m"),
        "date_last":  sub["date"].max().strftime("%Y-%m"),
    }


def _cross_manager_snapshot(df: pd.DataFrame, alloc: str) -> str:
    """Return current values for all managers for one allocation component."""
    sub = df[df["allocation_name"] == alloc].copy()
    if sub.empty:
        return "  (אין נתונים)"
    idx = sub.groupby(["manager", "track"])["date"].idxmax()
    snap = sub.loc[idx].sort_values("allocation_value", ascending=False)
    lines = []
    for _, row in snap.iterrows():
        lines.append(
            f"  {row['manager']} {row['track']}: {row['allocation_value']:.1f}%"
        )
    return "\n".join(lines)


# ── Prompt builders ───────────────────────────────────────────────────────────

def _build_full_prompt(display_df: pd.DataFrame, context: dict) -> str:
    """
    Build a comprehensive analysis prompt.
    context keys:
        managers, tracks, allocation_names, selected_range,
        date_min, date_max
    """
    managers         = context.get("managers", [])
    tracks           = context.get("tracks", [])
    allocation_names = context.get("allocation_names", [])
    sel_range        = context.get("selected_range", "הכל")

    # ── Section A: data summary per manager×track×alloc ──────────────────
    series_blocks = []
    all_stats = []

    for mgr in managers:
        for trk in tracks:
            for alloc in allocation_names:
                stats = _compute_stats(display_df, alloc, mgr, trk)
                if not stats:
                    continue
                all_stats.append({**stats, "manager": mgr, "track": trk, "alloc": alloc})
                series_text = _format_series_for_prompt(display_df, alloc, mgr, trk)
                series_blocks.append(
                    f"[{mgr} | {trk} | {alloc}]\n"
                    f"  טווח: {stats['date_first']} – {stats['date_last']}\n"
                    f"  נוכחי: {stats['current']}% | ממוצע: {stats['mean']}% | "
                    f"מינ׳: {stats['min']}% | מקס׳: {stats['max']}%\n"
                    f"  סטד: {stats['std']}pp | מגמה חודשית: {stats['slope_monthly']:+.2f}pp/חודש\n"
                    f"  נתונים ({stats['n_monthly']} חודשי, {stats['n_yearly']} שנתי):\n"
                    f"{series_text}"
                )

    # ── Section B: cross-manager comparison per alloc ─────────────────────
    cross_blocks = []
    for alloc in allocation_names:
        snapshot = _cross_manager_snapshot(display_df, alloc)
        cross_blocks.append(f"השוואה — {alloc} (ערך נוכחי לפי מנהל):\n{snapshot}")

    # ── Section C: risk signals ───────────────────────────────────────────
    risk_lines = []
    for s in all_stats:
        # High illiquid exposure risk
        if "סחיר" in s["alloc"] and s["current"] > 30:
            risk_lines.append(
                f"⚠️ {s['manager']} {s['track']}: חשיפה גבוהה ללא-סחיר ({s['current']}%) — "
                f"סיכון נזילות בולט."
            )
        # High volatility
        if s["std"] > 5:
            risk_lines.append(
                f"⚠️ {s['manager']} {s['track']} | {s['alloc']}: תנודתיות גבוהה "
                f"(סטד={s['std']}pp, שינוי מקסימלי={s['mom_max']}pp)."
            )
        # Strong downward trend
        if s["slope_monthly"] < -0.5:
            risk_lines.append(
                f"📉 {s['manager']} {s['track']} | {s['alloc']}: מגמת ירידה מובהקת "
                f"({s['slope_monthly']:+.2f}pp לחודש)."
            )
        # Strong upward trend
        if s["slope_monthly"] > 0.5:
            risk_lines.append(
                f"📈 {s['manager']} {s['track']} | {s['alloc']}: מגמת עלייה מובהקת "
                f"({s['slope_monthly']:+.2f}pp לחודש)."
            )

    risk_summary = "\n".join(risk_lines) if risk_lines else "לא זוהו אותות סיכון חריגים."

    # ── Assemble prompt ───────────────────────────────────────────────────
    series_section = "\n\n".join(series_blocks) or "(אין נתונים)"
    cross_section  = "\n\n".join(cross_blocks)  or "(אין נתונים)"

    prompt = f"""אתה אנליסט השקעות ישראלי בכיר המתמחה בגופים מוסדיים, קרנות פנסיה, ביטוח מנהלים וחיסכון ארוך-טווח.
לפניך נתוני חשיפות/אלוקציה היסטוריים של גופים מוסדיים.
(ש) = נתון שנתי, (ח) = נתון חודשי. טווח מוצג: {sel_range}.

══════════════════════════════
נתוני סדרות זמן לפי מנהל/מסלול/רכיב:
══════════════════════════════
{series_section}

══════════════════════════════
השוואה בין מנהלים (ערך נוכחי):
══════════════════════════════
{cross_section}

══════════════════════════════
אותות סיכון אוטומטיים:
══════════════════════════════
{risk_summary}

══════════════════════════════
בקשה לניתוח:
══════════════════════════════
כתוב ניתוח מקצועי מובנה בעברית בלבד, עם הכותרות הבאות בדיוק:

## ניתוח לפי גוף ומסלול
לכל מנהל בנפרד: מה האסטרטגיה שלו, מה השינויים העיקריים לאורך זמן, האם יש שינוי מגמה לאחרונה.

## השוואה בין גופים
מי מחזיק בחשיפה הגבוהה/נמוכה ביותר לכל רכיב. מי הכי תנודתי. מי שינה אסטרטגיה לאחרונה.

## ניתוח סיכון
חשיפה ללא-סחיר (סיכון נזילות), תנודתיות, ריכוזיות, האם יש גוף שנמצא בחשיפת קיצון.

## קשר לתשואה היסטורית
חשיפת מניות וחו"ל כמנועי תשואה אפשריים. גוף עם חשיפת מניות גבוהה יותר — מה הסיכוי לתשואה עודפת לטווח ארוך לעומת סיכון תנודתיות גבוה יותר לטווח קצר.

## יתרונות וחסרונות לפי גוף
לכל מנהל: יתרון מרכזי אחד וחסרון/סיכון מרכזי אחד, מבוסס על הנתונים.

## תובנה אסטרטגית
מה מספרים הנתונים על האסטרטגיה הכוללת של השוק? האם יש תנועה קולקטיבית? מה המשמעות למשקיע שבוחר בין הגופים?

כתוב בסגנון מקצועי, ממוקד, ומבוסס אך ורק על הנתונים שסופקו. אל תמציא נתונים. אל תציין שאתה AI."""

    return prompt


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class AnalysisResult:
    raw_text:  str = ""
    sections:  dict = field(default_factory=dict)
    error:     Optional[str] = None

    def parse_sections(self):
        """Split raw_text into named sections based on ## headers."""
        if not self.raw_text:
            return
        current_title = "כללי"
        current_lines: list[str] = []
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


# ── Main public API ───────────────────────────────────────────────────────────

def run_ai_analysis(
    display_df: pd.DataFrame,
    context: dict,
) -> AnalysisResult:
    """
    Run comprehensive AI analysis on the current display series.

    Parameters
    ----------
    display_df : the filtered/built display DataFrame
    context    : dict with keys: managers, tracks, allocation_names,
                 selected_range, date_min, date_max

    Returns
    -------
    AnalysisResult with .sections and .raw_text populated.
    """
    if display_df.empty:
        return AnalysisResult(error="אין נתונים לניתוח.")

    prompt = _build_full_prompt(display_df, context)
    text, err = _call_claude(prompt, max_tokens=1800)

    result = AnalysisResult(raw_text=text, error=err)
    if text:
        result.parse_sections()
    return result
