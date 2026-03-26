# -*- coding: utf-8 -*-
"""
reporting/final_report.py
─────────────────────────
Final Client Report Generation — post-optimization workflow.

Public API
──────────
    run_planning_ai(structured_input)  -> dict[section_name, text]
    render_final_report_ui(rows_list, recs, baseline, product_type)
        → renders the full UI block inside a Streamlit expander

AI Integration
──────────────
- mode = "planning" (as spec'd)
- Prompt sourced from Google Docs (same URL as ISA module)
- Structured JSON input only
- Returns exactly 6 sections
"""
from __future__ import annotations

import json
import math
import re
import os
from typing import Optional

# ── AI helpers (reuse from ai_analyst) ───────────────────────────────────────

_GUIDANCE_DOC_URL = (
    "https://docs.google.com/document/d/"
    "1Hqh9TI2u7QRbTvRAS0TRkyL-28-eLIznkQbGTd_M1Wk"
)
_NaN = float("nan")

SECTION_KEYS = [
    "executive_summary",
    "current_weaknesses",
    "planning_principles",
    "change_advantages",
    "risks_considerations",
    "final_summary",
]

# ── Notebook export constants ────────────────────────────────────────────────

NOTEBOOK_INSTRUCTIONS = {
    "language": "Hebrew (RTL)",
    "style": "professional family-office",
    "rules": [
        "Do NOT invent or extrapolate missing values",
        "When before-data is null/unavailable, present the field as unavailable — do not assume a value",
        "Build charts and tables only from valid numeric values (not null/undefined)",
        "Preserve Hebrew text and RTL layout throughout",
        "Use professional, balanced tone — not promotional",
        "Each slide must use only the data from its corresponding data/content field",
        "Do not merge or summarize slides — treat each slide as independent",
        "For partial reports: clearly label that this covers one product type only",
        "For full reports: reference the full portfolio scope",
    ],
    "missing_data_policy": (
        "If before-data is missing, show current state as the sole reference. "
        "Do NOT create comparison charts without valid before-values."
    ),
}


def _validate_export(pkg: dict) -> list[str]:
    """Return list of validation warnings before export. Empty = ready."""
    warnings_out = []
    pb = pkg.get("portfolio_before", {}) or {}
    pa = pkg.get("portfolio_after",  {}) or {}
    chg = pkg.get("changes_summary", []) or []

    has_any_before = any(
        v is not None
        for v in [pb.get("equities"), pb.get("abroad"), pb.get("sharpe")]
    )
    has_any_after = any(
        v is not None
        for v in [pa.get("equities"), pa.get("abroad"), pa.get("sharpe")]
    )
    if not has_any_after:
        warnings_out.append('לא ניתן להפיק דו"ח — חסרים נתוני תיק מוצע (אחרי)')
    if not has_any_before:
        warnings_out.append('לא ניתן להפיק דו"ח מלא כי חסרים נתוני מצב קיים (לפני). הדו"ח יופק כדוח חלקי.')
    if not pkg.get("ai_sections", {}).get("executive_summary", "").strip():
        warnings_out.append('הסבר AI טרם נוצר — ניתן לייצא ללא הסבר AI, אך מומלץ להפיק קודם.')
    return warnings_out


SECTION_LABELS_HE = {
    "executive_summary":     "1. תקציר מנהלים",
    "current_weaknesses":    "2. חולשות התיק הנוכחי",
    "planning_principles":   "3. עקרונות התכנון",
    "change_advantages":     "4. יתרונות השינויים המוצעים",
    "risks_considerations":  "5. שיקולים ואיזונים",
    "final_summary":         "6. סיכום סופי",
}


def _get_api_key() -> str:
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "OPENAI_API_KEY" in st.secrets:
            return str(st.secrets["OPENAI_API_KEY"])
    except Exception:
        pass
    return os.getenv("OPENAI_API_KEY", "")


def _fetch_guidance() -> str:
    """Fetch AI writing instructions from the canonical Google Doc."""
    import requests
    doc_id = re.search(r"/d/([^/]+)", _GUIDANCE_DOC_URL)
    if not doc_id:
        return ""
    did = doc_id.group(1)
    for url in [
        f"https://docs.google.com/document/d/{did}/export?format=txt",
        f"https://docs.google.com/document/u/0/d/{did}/export?format=txt",
    ]:
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            if r.status_code == 200:
                txt = r.text.strip()
                if txt and "JavaScript" not in txt[:300]:
                    return txt
        except Exception:
            pass
    return ""


def _fmt(v, pct=True) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "לא זמין"
    if pct:
        return f"{v:.1f}%"
    return f"{v:.2f}"


def _build_planning_prompt(structured: dict, guidance: str) -> str:
    """Build the planning-mode AI prompt from structured JSON input."""
    pb   = structured.get("portfolio_before", {})
    pa   = structured.get("portfolio_after", {})
    obj  = structured.get("client_objectives", {})
    sol  = structured.get("selected_solution_name", "")
    chg  = structured.get("changes_summary", {})

    before_block = (
        f"  מניות: {_fmt(pb.get('equities'))}\n"
        f"  חו\"ל: {_fmt(pb.get('abroad'))}\n"
        f"  מט\"ח: {_fmt(pb.get('fx'))}\n"
        f"  לא-סחיר: {_fmt(pb.get('illiquid'))}\n"
        f"  שארפ: {_fmt(pb.get('sharpe'), pct=False)}\n"
        f"  עלות שירות: {_fmt(pb.get('cost'))}\n"
        f"  מנהלים: {pb.get('managers_count', 'לא זמין')}\n"
        f"  מוצרים: {pb.get('products_count', 'לא זמין')}"
    )
    after_block = (
        f"  מניות: {_fmt(pa.get('equities'))}\n"
        f"  חו\"ל: {_fmt(pa.get('abroad'))}\n"
        f"  מט\"ח: {_fmt(pa.get('fx'))}\n"
        f"  לא-סחיר: {_fmt(pa.get('illiquid'))}\n"
        f"  שארפ: {_fmt(pa.get('sharpe'), pct=False)}\n"
        f"  עלות שירות: {_fmt(pa.get('cost'))}\n"
        f"  מנהלים: {pa.get('managers_count', 'לא זמין')}\n"
        f"  מוצרים: {pa.get('products_count', 'לא זמין')}"
    )
    obj_block = (
        f"  יעד מניות: {_fmt(obj.get('target_equities'))}\n"
        f"  יעד חו\"ל: {_fmt(obj.get('target_abroad'))}\n"
        f"  יעד מט\"ח: {_fmt(obj.get('target_fx'))}\n"
        f"  יעד לא-סחיר: {_fmt(obj.get('target_illiquid'))}\n"
        f"  עדיפות: {obj.get('primary_rank', 'דיוק')}\n"
        f"  עולם מוצר: {obj.get('product_type', 'לא צוין')}"
    )
    delta_block = "\n".join(
        f"  {k}: {_fmt(v, pct=True)}" for k, v in chg.items()
    ) or "  (אין נתוני דלתא)"

    guidance_section = (
        f"הנחיות כתיבה ממסמך חיצוני:\n{guidance}"
        if guidance
        else "לא נטענו הנחיות חיצוניות. היצמד לנתונים בלבד."
    )

    return f"""mode: planning
נושא: הפקת דוח לקוח לאחר אופטימיזציית תמהיל.

נתוני הקלט הם JSON מובנה בלבד. אל תסיק מעבר לנתונים שנמסרו לך.

--- תיק נוכחי (לפני) ---
{before_block}

--- תיק מוצע (אחרי) ---
{after_block}

--- יעדי הלקוח ---
{obj_block}

--- שם החלופה שנבחרה ---
{sol or "לא צוין"}

--- שינויים מרכזיים (דלתא) ---
{delta_block}

---
{guidance_section}

---
הוראות תפוקה — חובה לפי הסדר הזה בדיוק:

כתוב בעברית. כל סעיף מתחיל בכותרת מפורשת:
[1. תקציר מנהלים]
[2. חולשות התיק הנוכחי]
[3. עקרונות התכנון]
[4. יתרונות השינויים המוצעים]
[5. שיקולים ואיזונים]
[6. סיכום סופי]

דרישות:
- אל תמציא נתונים שאינם בקלט
- אל תיתן ייעוץ השקעות מחייב
- הבהר את השיפור בפיזור הסיכון
- התייחס לחשיפה גלובלית, ריכוז ויעדי הלקוח
- טון: מקצועי, מאוזן, מבוסס-דאטה
- אל תשתמש בנוסח ודאות מוחלטת"""


def _parse_sections(text: str) -> dict[str, str]:
    """Parse 6 bracketed sections from the AI response."""
    patterns = {
        "executive_summary":    r"\[1\.[^\]]*\]",
        "current_weaknesses":   r"\[2\.[^\]]*\]",
        "planning_principles":  r"\[3\.[^\]]*\]",
        "change_advantages":    r"\[4\.[^\]]*\]",
        "risks_considerations": r"\[5\.[^\]]*\]",
        "final_summary":        r"\[6\.[^\]]*\]",
    }
    result = {k: "" for k in SECTION_KEYS}
    positions = []
    for key, pat in patterns.items():
        m = re.search(pat, text)
        if m:
            positions.append((m.start(), key, m.end()))

    positions.sort()
    for i, (start, key, end) in enumerate(positions):
        next_start = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        result[key] = text[end:next_start].strip()

    # Fallback: if parse fails, put everything in executive_summary
    if all(v == "" for v in result.values()):
        result["executive_summary"] = text.strip()
    return result


def run_planning_ai(structured_input: dict) -> tuple[dict[str, str], Optional[str]]:
    """
    Call AI in planning mode with structured JSON input.
    Returns (sections_dict, error_string_or_None).
    """
    try:
        from institutional_strategy_analysis.ai_analyst import _call_claude
    except ImportError:
        # Fallback: direct HTTP call using the same pattern
        def _call_claude(prompt, system="", max_tokens=4000, model="gpt-4o"):
            import requests as _r
            key = _get_api_key()
            if not key:
                return "", "לא הוגדר מפתח OPENAI_API_KEY."
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": prompt})
            try:
                resp = _r.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": model, "max_tokens": max_tokens, "messages": msgs},
                    timeout=90,
                )
                if resp.status_code == 200:
                    t = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    return (t, None) if t else ("", "תגובה ריקה.")
                return "", f"שגיאת API: HTTP {resp.status_code}"
            except Exception as e:
                return "", f"שגיאת תקשורת: {e}"

    guidance = _fetch_guidance()
    prompt   = _build_planning_prompt(structured_input, guidance)
    system   = (
        "אתה יועץ השקעות המנתח תיקי השקעות בעברית. "
        "עבד במצב planning — הפקת דוח לקוח לאחר אופטימיזציה. "
        "היצמד לנתונים שנמסרו, אל תסיק מעבר למה שנמסר, "
        "ואל תיתן ייעוץ השקעות מחייב."
    )
    raw, err = _call_claude(prompt, system=system, max_tokens=4000)
    if err:
        return {k: "" for k in SECTION_KEYS}, err
    return _parse_sections(raw), None


def _clean_for_json(obj):
    """Recursively replace float NaN/Inf with None for clean JSON output."""
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else round(obj, 4)
    if isinstance(obj, dict):
        return {k: _clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean_for_json(v) for v in obj]
    return obj


def _comparison_rows(pb: dict, pa: dict) -> list:
    """Build a structured comparison table for the data slide."""
    keys = [
        ("מניות",    "equities"),
        ('חו"ל',    "abroad"),
        ('מט"ח',    "fx"),
        ("לא-סחיר", "illiquid"),
        ("שארפ",     "sharpe"),
        ("עלות %",   "cost"),
    ]
    rows = []
    for label, key in keys:
        before = pb.get(key)
        after  = pa.get(key)
        if before is None and after is None:
            continue
        delta = None
        if before is not None and after is not None:
            delta = round(after - before, 2)
        rows.append({
            "metric": label,
            "before": before,
            "after":  after,
            "delta":  delta,
        })
    return rows


def build_notebook_package(
    structured_input: dict,
    sections: dict[str, str],
    product_type: str = "",
    report_mode: str = "partial",
) -> str:
    """
    Build a production-ready Notebook JSON payload.
    - All NaN/Inf replaced with None (valid JSON null)
    - Slides typed: cover / text / data / table
    - No JSON-in-strings
    - Full schema with validation metadata
    """
    pb  = _clean_for_json(structured_input.get("portfolio_before",  {})) or {}
    pa  = _clean_for_json(structured_input.get("portfolio_after",   {})) or {}
    obj = _clean_for_json(structured_input.get("client_objectives", {})) or {}
    sel = structured_input.get("selected_solution_name", "")

    # Build comparison rows — always include all 6 metrics, null when missing
    comparison_rows = []
    METRICS = [
        ("\u05de\u05e0\u05d9\u05d5\u05ea",   "equities"),
        ('\u05d7\u05d5"\u05dc',               "abroad"),
        ('\u05de\u05d8"\u05d7',               "fx"),
        ("\u05dc\u05d0-\u05e1\u05d7\u05d9\u05e8", "illiquid"),
        ("\u05e9\u05d0\u05e8\u05e4", "sharpe"),
        ("\u05e2\u05dc\u05d5\u05ea %",  "cost"),
    ]
    for label, key in METRICS:
        bv = pb.get(key)
        av = pa.get(key)
        dv = round(av - bv, 2) if (bv is not None and av is not None) else None
        note = None if bv is not None else "\u05d0\u05d9\u05df \u05e0\u05ea\u05d5\u05e0\u05d9 \u05de\u05e6\u05d1 \u05e7\u05d9\u05d9\u05dd"
        comparison_rows.append({
            "metric":            label,
            "before":            bv,
            "after":             av,
            "delta":             dv,
            "availability_note": note,
        })

    # Data completeness
    has_before = any(r["before"] is not None for r in comparison_rows)
    has_after  = any(r["after"]  is not None for r in comparison_rows)
    data_completeness = (
        "full"    if has_before and has_after else
        "partial" if has_after else
        "none"
    )

    slides = [
        {
            "slide":   1,
            "type":    "cover",
            "title":   "\u05e9\u05e2\u05e8",
            "content": f"\u05d3\u05d5\"\u05d7 \u05dc\u05e7\u05d5\u05d7 \u2014 {product_type or '\u05d0\u05d5\u05e4\u05d8\u05d9\u05de\u05d9\u05d6\u05e6\u05d9\u05d9\u05ea \u05ea\u05de\u05d4\u05d9\u05dc'}",
            "subtitle": "\u05d4\u05d5\u05e4\u05e7 \u05e2\u05dc-\u05d9\u05d3\u05d9 Profit Financial Group \u00b7 Alpha Optimizer",
            "report_type": "\u05d3\u05d5\"\u05d7 \u05de\u05dc\u05d0 \u05dc\u05db\u05dc\u05dc \u05d4\u05ea\u05d9\u05e7" if report_mode == "full" else f"\u05d3\u05d5\"\u05d7 \u05d7\u05dc\u05e7\u05d9 \u2014 {product_type}",
        },
        {
            "slide":   2,
            "type":    "text",
            "title":   "\u05ea\u05e7\u05e6\u05d9\u05e8 \u05de\u05e0\u05d4\u05dc\u05d9\u05dd",
            "content": sections.get("executive_summary", ""),
        },
        {
            "slide":   3,
            "type":    "data",
            "title":   "\u05ea\u05d9\u05e7 \u05e0\u05d5\u05db\u05d7\u05d9",
            "content": "\u05e0\u05ea\u05d5\u05e0\u05d9 \u05ea\u05d9\u05e7 \u05d4\u05d4\u05e9\u05e7\u05e2\u05d5\u05ea \u05e2\u05dc-\u05e4\u05d9 \u05d9\u05d9\u05d1\u05d5\u05d0 \u05de\u05e1\u05dc\u05e7\u05d4" if not has_before else "\u05e0\u05ea\u05d5\u05e0\u05d9 \u05ea\u05d9\u05e7 \u05d4\u05dc\u05e7\u05d5\u05d7 \u05dc\u05e4\u05e0\u05d9 \u05d4\u05e9\u05d9\u05e0\u05d5\u05d9",
            "data":    pb,
            "availability": "available" if has_before else "unavailable",
        },
        {
            "slide":   4,
            "type":    "data",
            "title":   "\u05ea\u05d9\u05e7 \u05de\u05d5\u05e6\u05e2",
            "content": f"\u05d7\u05dc\u05d5\u05e4\u05d4 \u05e0\u05d1\u05d7\u05e8\u05ea: {sel}",
            "data":    pa,
            "availability": "available" if has_after else "unavailable",
        },
        {
            "slide":    5,
            "type":     "table",
            "title":    "\u05d4\u05e9\u05d5\u05d5\u05d0\u05d4 \u05dc\u05e4\u05e0\u05d9 / \u05d0\u05d7\u05e8\u05d9",
            "content":  "\u05d4\u05e9\u05d9\u05e0\u05d5\u05d9\u05dd \u05d4\u05de\u05e8\u05db\u05d6\u05d9\u05d9\u05dd \u05d1\u05ea\u05d9\u05e7",
            "data":     comparison_rows,
            "columns":  ["metric", "before", "after", "delta", "availability_note"],
            "has_full_comparison": has_before and has_after,
        },
        {
            "slide":   6,
            "type":    "text",
            "title":   "\u05d9\u05ea\u05e8\u05d5\u05e0\u05d5\u05ea \u05d4\u05e9\u05d9\u05e0\u05d5\u05d9\u05d9\u05dd",
            "content": sections.get("change_advantages", ""),
        },
        {
            "slide":   7,
            "type":    "text",
            "title":   "\u05e9\u05d9\u05e7\u05d5\u05dc\u05d9\u05dd \u05d5\u05d0\u05d9\u05d6\u05d5\u05e0\u05d9\u05dd",
            "content": sections.get("risks_considerations", ""),
        },
        {
            "slide":   8,
            "type":    "text",
            "title":   "\u05e1\u05d9\u05db\u05d5\u05dd \u05e1\u05d5\u05e4\u05d9",
            "content": sections.get("final_summary", ""),
        },
    ]

    pkg = {
        "notebook_schema_version": "3.0",
        "mode":                    "planning",
        "report_mode":             report_mode,
        "export_ready":            has_after,
        "data_completeness":       data_completeness,
        "product_type":            product_type,
        "selected_solution":       sel,
        "client_objectives":       obj,
        "portfolio_before":        pb,
        "portfolio_after":         pa,
        "changes_summary":         comparison_rows,
        "ai_sections":             sections,
        "presentation_slides":     slides,
        "notebook_instructions":   NOTEBOOK_INSTRUCTIONS,
        "presentation_prompt": (
            f"\u05e6\u05d5\u05e8 \u05de\u05e6\u05d2\u05ea \u05de\u05e7\u05e6\u05d5\u05e2\u05d9\u05ea \u05d1\u05e2\u05d1\u05e8\u05d9\u05ea \u05d4\u05db\u05d5\u05dc\u05dc\u05ea 8 \u05e9\u05e7\u05d5\u05e4\u05d9\u05d5\u05ea. "
            f"\u05d6\u05d4\u05d5 {'\u05d3\u05d5\"\u05d7 \u05de\u05dc\u05d0' if report_mode == 'full' else '\u05d3\u05d5\"\u05d7 \u05d7\u05dc\u05e7\u05d9 \u05dc\u05e2\u05d5\u05dc\u05dd \u05de\u05d5\u05e6\u05e8 \u05d1\u05d5\u05d3\u05d3'}. "
            f"\u05de\u05e6\u05d1 \u05e0\u05ea\u05d5\u05e0\u05d9\u05dd: {data_completeness}. "
            "\u05e9\u05e7\u05d5\u05e4\u05d9\u05d5\u05ea \u05de\u05e1\u05d5\u05d2 data \u2014 \u05d4\u05e6\u05d2 \u05db\u05d8\u05d1\u05dc\u05d0\u05d5\u05ea \u05d0\u05d5 \u05ea\u05e8\u05e9\u05d9\u05de\u05d9\u05dd \u05e2\u05dd \u05d4\u05e9\u05d3\u05d5\u05ea \u05de-data. "
            "\u05e9\u05e7\u05d5\u05e4\u05d9\u05d5\u05ea \u05de\u05e1\u05d5\u05d2 table \u2014 \u05d4\u05e6\u05d2 \u05db\u05d8\u05d1\u05dc\u05ea \u05d4\u05e9\u05d5\u05d5\u05d0\u05d4 \u05e2\u05dd \u05e2\u05de\u05d5\u05d3\u05d5\u05ea before/after/delta. "
            "\u05db\u05d0\u05e9\u05e8 before \u05d4\u05d5\u05d0 null \u2014 \u05d0\u05dc \u05ea\u05d9\u05e6\u05d5\u05e8 \u05d2\u05e8\u05e3 \u05d4\u05e9\u05d5\u05d5\u05d0\u05d4, \u05d4\u05e6\u05d2 \u05e8\u05e7 \u05e2\u05de\u05d5\u05d3\u05ea after. "
            "\u05d0\u05dc \u05ea\u05de\u05e6\u05d0 \u05e2\u05e8\u05db\u05d9\u05dd \u05d7\u05e1\u05e8\u05d9\u05dd."
        ),
    }
    return json.dumps(pkg, ensure_ascii=False, indent=2)

# ── Streamlit UI ──────────────────────────────────────────────────────────────

def render_final_report_ui(
    rows_list: list,
    recs: dict,
    baseline: Optional[dict],
    product_type: str,
) -> None:
    """
    Renders the Final Client Report expander section.
    Call this immediately after render_results_table() in streamlit_app.py.
    """
    import streamlit as st

    _nan = float("nan")

    def _f(v) -> float:
        try:
            f = float(v)
            return _nan if math.isnan(f) else f
        except (TypeError, ValueError):
            return _nan


    # ── Step 1: Build structured input ────────────────────────────
    bl   = baseline or {}
    best = (recs.get("weighted") or recs.get("accurate") or
            recs.get("sharpe")  or recs.get("service") or {})

    # Portfolio before
    pb = {
        "equities":       _f(bl.get("stocks")),
        "abroad":         _f(bl.get("foreign")),
        "fx":             _f(bl.get("fx")),
        "illiquid":       _f(bl.get("illiquid")),
        "sharpe":         _f(bl.get("sharpe")),
        "cost":           _f(bl.get("service")),
        "managers_count": int(bl.get("managers_count", 0)) if bl else 0,
        "products_count": int(bl.get("products_count", 0)) if bl else 0,
    }

    # Portfolio after
    pa = {
        "equities": _f(best.get("מניות (%)")),
        "abroad":   _f(best.get('חו"ל (%)')),
        "fx":       _f(best.get('מט"ח (%)')),
        "illiquid": _f(best.get("לא־סחיר (%)")),
        "sharpe":   _f(best.get("שארפ משוקלל")),
        "cost":     _f(best.get("שירות משוקלל")),
        "managers_count": (
            len(set(best.get("מנהלים", "").split("|")))
            if best.get("מנהלים") else 0
        ),
        "products_count": (
            len(best.get("weights", ())) if best.get("weights") else 0
        ),
    }

    # Changes delta
    changes: dict = {}
    for human_k, pb_k, pa_k in [
        ("מניות",    "equities", "equities"),
        ('חו"ל',     "abroad",   "abroad"),
        ('מט"ח',     "fx",       "fx"),
        ("לא-סחיר", "illiquid", "illiquid"),
    ]:
        before_v = pb.get(pb_k, _nan)
        after_v  = pa.get(pa_k, _nan)
        if not (math.isnan(before_v) or math.isnan(after_v)):
            changes[human_k] = round(after_v - before_v, 1)

    # Objectives from session state
    tgts = dict(st.session_state.get("targets", {}))
    obj = {
        "target_equities": _f(tgts.get("stocks")),
        "target_abroad":   _f(tgts.get("foreign")),
        "target_fx":       _f(tgts.get("fx")),
        "target_illiquid": _f(tgts.get("illiquid")),
        "primary_rank":    st.session_state.get("primary_rank", "דיוק"),
        "product_type":    product_type,
    }

    selected_alt_name = str(st.session_state.get("selected_alt") or best.get("חלופה", "חלופה מומלצת"))

    structured_input = {
        "portfolio_before":       pb,
        "portfolio_after":        pa,
        "client_objectives":      obj,
        "selected_solution_name": selected_alt_name,
        "changes_summary":        changes,
    }

    # ── Step 1 display: Before / After summary ────────────────────
    st.subheader("שלב 1 — השוואת תיק לפני ואחרי")
    _c1, _c2 = st.columns(2, gap="medium")
    with _c1:
        st.markdown("**📂 תיק נוכחי**")
        _rows_before = [
            ("מניות",    f"{pb['equities']:.1f}%" if not math.isnan(pb['equities'])  else "—"),
            ('חו"ל',     f"{pb['abroad']:.1f}%"   if not math.isnan(pb['abroad'])    else "—"),
            ('מט"ח',     f"{pb['fx']:.1f}%"        if not math.isnan(pb['fx'])        else "—"),
            ("לא-סחיר", f"{pb['illiquid']:.1f}%"  if not math.isnan(pb['illiquid']) else "—"),
            ("שארפ",     f"{pb['sharpe']:.2f}"     if not math.isnan(pb['sharpe'])    else "—"),
            ("עלות",     f"{pb['cost']:.2f}%"      if not math.isnan(pb['cost'])      else "—"),
        ]
        for label, val in _rows_before:
            st.markdown(f"- **{label}:** {val}")

    with _c2:
        st.markdown(f"**🎯 תיק מוצע — {selected_alt_name}**")
        _rows_after = [
            ("מניות",    f"{pa['equities']:.1f}%" if not math.isnan(pa['equities'])  else "—"),
            ('חו"ל',     f"{pa['abroad']:.1f}%"   if not math.isnan(pa['abroad'])    else "—"),
            ('מט"ח',     f"{pa['fx']:.1f}%"        if not math.isnan(pa['fx'])        else "—"),
            ("לא-סחיר", f"{pa['illiquid']:.1f}%"  if not math.isnan(pa['illiquid']) else "—"),
            ("שארפ",     f"{pa['sharpe']:.2f}"     if not math.isnan(pa['sharpe'])    else "—"),
            ("עלות",     f"{pa['cost']:.2f}%"      if not math.isnan(pa['cost'])      else "—"),
        ]
        for label, val in _rows_after:
            st.markdown(f"- **{label}:** {val}")

    if changes:
        st.markdown("**📊 שינויים עיקריים:**")
        _delta_cols = st.columns(len(changes))
        for _dc, (k, v) in zip(_delta_cols, changes.items()):
            _dc.metric(k, f"{v:+.1f}pp", delta=f"{v:+.1f}pp",
                       delta_color="normal" if v >= 0 else "inverse")

    st.divider()

    # ── Step 2: AI generation ────────────────────────────────────
    st.subheader("שלב 2 — הסבר AI (מצב: planning)")

    if "final_report_sections" not in st.session_state:
        st.session_state["final_report_sections"] = {}
    if "final_report_structured" not in st.session_state:
        st.session_state["final_report_structured"] = {}

    _ai_col, _ = st.columns([1.2, 2])
    with _ai_col:
        if st.button("🤖 הפק הסבר AI", key="btn_planning_ai", type="primary"):
            with st.spinner("מגדיר שאלת planning ושולח ל-AI..."):
                _secs, _err = run_planning_ai(structured_input)
            if _err:
                st.error(f"⚠️ שגיאת AI: {_err}")
            else:
                st.session_state["final_report_sections"]   = _secs
                st.session_state["final_report_structured"] = structured_input
                st.success("✅ הסבר AI נוצר בהצלחה")
                st.rerun()

    _secs = st.session_state.get("final_report_sections", {})

    if _secs:
        st.divider()
        # ── Step 3: User editing ──────────────────────────────────
        st.subheader("שלב 3 — עריכה ואישור")

        _tone = st.radio(
            "טון הכתיבה",
            ["מקצועי", "פשוט ונגיש", "שכנועי"],
            horizontal=True,
            key="final_report_tone",
            help="בחר טון — לאחר מכן לחץ 'הפק מחדש' לקבל טקסט מותאם",
        )

        _edited = {}
        for key in SECTION_KEYS:
            label = SECTION_LABELS_HE[key]
            default_text = _secs.get(key, "")
            _edited[key] = st.text_area(
                label,
                value=default_text,
                height=130,
                key=f"final_sec_{key}",
                help="ניתן לערוך חופשי. לחץ 'הפק מחדש' לקבל גרסה חדשה מ-AI.",
            )

        _re_col, _save_col, _ = st.columns([1, 1, 3])
        with _re_col:
            if st.button("🔄 הפק מחדש", key="btn_regen_ai", type="secondary"):
                # Adjust prompt based on tone
                _tone_instr = {
                    "מקצועי":      "כתוב בטון מקצועי ורשמי.",
                    "פשוט ונגיש": "כתוב בשפה פשוטה, נגישה ללקוח שאינו מומחה.",
                    "שכנועי":      "כתוב בטון שכנועי שמדגיש את יתרונות השינויים.",
                }.get(_tone, "")
                _mod_input = dict(structured_input)
                _mod_input["tone_instruction"] = _tone_instr
                with st.spinner("מפיק מחדש..."):
                    _new_secs, _err2 = run_planning_ai(_mod_input)
                if _err2:
                    st.error(f"⚠️ {_err2}")
                else:
                    st.session_state["final_report_sections"] = _new_secs
                    st.rerun()

        with _save_col:
            if st.button("💾 שמור עריכות", key="btn_save_edits", type="secondary"):
                st.session_state["final_report_sections"] = _edited
                st.success("עריכות נשמרו ✅")

        st.divider()

        # ── Step 4: Export ────────────────────────────────────────
        st.markdown("""
<div style="background:#0f172a;border-radius:12px;padding:12px 18px;
     direction:rtl;text-align:right;margin-bottom:14px">
  <div style="font-size:14px;font-weight:900;color:#f1f5f9;margin-bottom:2px">
    שלב 4 — ייצוא חבילת Notebook
  </div>
  <div style="font-size:11.5px;color:#94a3b8">
    הורד את חבילת ה-JSON · העלה ל-NotebookLM / Colab · קבל מצגת מלאה
  </div>
</div>""", unsafe_allow_html=True)

        _approved_secs = {
            k: st.session_state.get(f"final_sec_{k}", _secs.get(k, ""))
            for k in SECTION_KEYS
        }
        _is_full_report = st.session_state.get("journey_portfolio_optimization_done", False)
        _r_mode = "full" if _is_full_report else "partial"
        _pkg_str = build_notebook_package(
            structured_input, _approved_secs, product_type, report_mode=_r_mode
        )

        # ── Pre-export validation summary ─────────────────────────────
        import json as _json_mod
        _pkg_parsed = _json_mod.loads(_pkg_str)
        _warnings = _validate_export(_pkg_parsed)
        _export_ready = _pkg_parsed.get("export_ready", False)
        _data_complete = _pkg_parsed.get("data_completeness", "none")
        _scope_lbl = 'דו"ח מלא — כלל התיק' if _is_full_report else f'דו"ח חלקי — {product_type}'
        _scope_bg  = "#d1fae5" if _is_full_report else "#fef3c7"
        _scope_c   = "#065f46" if _is_full_report else "#92400e"

        # Summary strip
        st.markdown(f"""
<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;
     padding:12px 16px;direction:rtl;text-align:right;margin-bottom:12px">
  <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
    <div>
      <div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;
           letter-spacing:1.5px;margin-bottom:3px">סוג דוח</div>
      <span style="background:{_scope_bg};color:{_scope_c};font-size:11px;font-weight:700;
        padding:3px 10px;border-radius:999px">{_scope_lbl}</span>
    </div>
    <div>
      <div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;
           letter-spacing:1.5px;margin-bottom:3px">השלמות נתונים</div>
      <span style="font-size:12px;font-weight:700;color:{'#065f46' if _data_complete == 'full' else '#92400e'}">
        {'מלא ✓' if _data_complete == 'full' else ('חלקי ⚠' if _data_complete == 'partial' else 'חסר ✗')}
      </span>
    </div>
    <div>
      <div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;
           letter-spacing:1.5px;margin-bottom:3px">הסבר AI</div>
      <span style="font-size:12px;font-weight:700;color:{'#065f46' if _approved_secs.get('executive_summary','').strip() else '#92400e'}">
        {'קיים ✓' if _approved_secs.get('executive_summary','').strip() else 'חסר ⚠'}
      </span>
    </div>
    <div>
      <div style="font-size:9px;font-weight:700;color:#64748b;text-transform:uppercase;
           letter-spacing:1.5px;margin-bottom:3px">מוכן לייצוא</div>
      <span style="font-size:12px;font-weight:700;color:{'#065f46' if _export_ready else '#92400e'}">
        {'כן ✓' if _export_ready else 'לא עדיין ✗'}
      </span>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

        # Show validation warnings if any
        for _w in _warnings:
            if "לא ניתן" in _w:
                st.error(f"🚫 {_w}")
            else:
                st.warning(f"⚠️ {_w}")

        _ex1, _ex2, _ = st.columns([1.3, 1.2, 3.5])
        with _ex1:
            st.download_button(
                "📦 הורד חבילת Notebook (JSON)",
                data=_pkg_str.encode("utf-8"),
                file_name="client_report_notebook.json",
                mime="application/json",
                key="dl_notebook_pkg",
                help="העלה ל-NotebookLM או Colab | schema v3.0 | אין NaN",
                disabled=(not _export_ready),
            )
        with _ex2:
            _plain = "\n\n".join(
                f"{SECTION_LABELS_HE[k]}\n{'-'*40}\n{_approved_secs.get(k,'')}"
                for k in SECTION_KEYS
            )
            st.download_button(
                "📄 הורד טקסט (.txt)",
                data=_plain.encode("utf-8"),
                file_name="client_report_text.txt",
                mime="text/plain",
                key="dl_text_report",
            )
        st.caption(
            f"schema v3.0 · report_mode={_r_mode} · slides=8 · "
            f"data_completeness={_data_complete}"
        )
