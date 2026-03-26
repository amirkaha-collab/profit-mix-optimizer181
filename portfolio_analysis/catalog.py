# -*- coding: utf-8 -*-
"""
portfolio_analysis/catalog.py
──────────────────────────────
Product type registry + catalog helper layer.

Responsibilities:
- Canonical product type list (normalized, no plural/singular drift)
- Supported (catalog-driven) vs manual-only product types
- Catalog lookup from df_long: managers → funds → tracks
- Preview data builder

All UI logic stays in ui.py.
This module contains only data / lookup logic.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd


# ── Canonical product type registry ──────────────────────────────────────────

# Tab names in the app (as loaded from GSheets — these are the df_long-compatible names)
# Each entry maps  display_name -> canonical_name  and  is_catalog_supported
_CATALOG_REGISTRY: list[dict] = [
    # Catalog-supported types (have data in df_long)
    {"canonical": "קרן השתלמות",         "tab": "קרנות השתלמות",    "catalog": True,  "aliases": ["קרנות השתלמות","השתלמות"]},
    {"canonical": "פוליסת חיסכון",        "tab": "פוליסות חיסכון",   "catalog": True,  "aliases": ["פוליסות חיסכון","פוליסה","פוליסות"]},
    {"canonical": "קרן פנסיה",           "tab": "קרנות פנסיה",     "catalog": True,  "aliases": ["קרנות פנסיה","פנסיה"]},
    {"canonical": "קופת גמל",            "tab": "קופות גמל",       "catalog": True,  "aliases": ["קופות גמל","גמל","קופות"]},
    {"canonical": "קופת גמל להשקעה",     "tab": "גמל להשקעה",      "catalog": True,  "aliases": ["גמל להשקעה","קופת גמל להשקעה","גמל להשקעה"]},
    {"canonical": "ביטוח מנהלים",        "tab": "פוליסות חיסכון",   "catalog": True,  "aliases": ["ביטוח מנהלים","ביטוח"]},
    {"canonical": "קופה מרכזית לפיצויים","tab": "קופות גמל",       "catalog": True,  "aliases": ["קופה מרכזית לפיצויים","פיצויים"]},
    # Manual-only types (no df_long data)
    {"canonical": "נדל\"ן בארץ",          "tab": None, "catalog": False, "aliases": ["נדל\"ן בארץ","נדלן בארץ"]},
    {"canonical": "נדל\"ן בחו\"ל",         "tab": None, "catalog": False, "aliases": ["נדל\"ן בחו\"ל","נדלן בחול"]},
    {"canonical": "תיק מנוהל",           "tab": None, "catalog": False, "aliases": ["תיק מנוהל"]},
    {"canonical": "תיק השקעות בחו\"ל",    "tab": None, "catalog": False, "aliases": ["תיק השקעות בחו\"ל","תיק חול"]},
    {"canonical": "קרן גידור",           "tab": None, "catalog": False, "aliases": ["קרן גידור"]},
    {"canonical": "קרן השקעות",          "tab": None, "catalog": False, "aliases": ["קרן השקעות"]},
    {"canonical": "עו\"ש",               "tab": None, "catalog": False, "aliases": ["עו\"ש","עוש"]},
    {"canonical": "קרן נאמנות",          "tab": None, "catalog": False, "aliases": ["קרן נאמנות","נאמנות"]},
    {"canonical": "פיקדון",             "tab": None, "catalog": False, "aliases": ["פיקדון"]},
    {"canonical": "קריפטו",             "tab": None, "catalog": False, "aliases": ["קריפטו","crypto"]},
    {"canonical": "אחר",               "tab": None, "catalog": False, "aliases": ["אחר","other"]},
]

# All display names for the add-product dropdown
ALL_PRODUCT_TYPES: list[str] = [r["canonical"] for r in _CATALOG_REGISTRY]

# Only the catalog-supported ones
SUPPORTED_CATALOG_TYPES: list[str] = [r["canonical"] for r in _CATALOG_REGISTRY if r["catalog"]]

# Manual-only
MANUAL_ONLY_TYPES: list[str] = [r["canonical"] for r in _CATALOG_REGISTRY if not r["catalog"]]

# Tab name → canonical type (for df_long context)
_TAB_TO_CANONICAL: dict[str, str] = {
    "קרנות השתלמות":  "קרן השתלמות",
    "פוליסות חיסכון": "פוליסת חיסכון",
    "קרנות פנסיה":    "קרן פנסיה",
    "קופות גמל":      "קופת גמל",
    "גמל להשקעה":     "קופת גמל להשקעה",
}

# canonical → tab name (which df_long to use)
_CANONICAL_TO_TAB: dict[str, str] = {
    "קרן השתלמות":         "קרנות השתלמות",
    "פוליסת חיסכון":       "פוליסות חיסכון",
    "ביטוח מנהלים":        "פוליסות חיסכון",
    "קרן פנסיה":           "קרנות פנסיה",
    "קופת גמל":            "קופות גמל",
    "קופה מרכזית לפיצויים": "קופות גמל",
    "קופת גמל להשקעה":    "גמל להשקעה",
}


# ── Normalization ────────────────────────────────────────────────────────────

def normalize_product_type(raw: str) -> str:
    """
    Normalize any product type variant to the canonical form.
    E.g. "קרנות השתלמות" → "קרן השתלמות"
         "גמל להשקעה"   → "קופת גמל להשקעה"
    Returns the input unchanged if no match found.
    """
    raw = (raw or "").strip()
    rl  = raw.lower()
    for entry in _CATALOG_REGISTRY:
        if raw == entry["canonical"]:
            return raw
        for alias in entry["aliases"]:
            if rl == alias.lower():
                return entry["canonical"]
    return raw


def get_product_entry_mode(product_type: str) -> str:
    """Return 'catalog' or 'manual'."""
    pt = normalize_product_type(product_type)
    for entry in _CATALOG_REGISTRY:
        if entry["canonical"] == pt:
            return "catalog" if entry["catalog"] else "manual"
    return "manual"


def is_catalog_supported(product_type: str) -> bool:
    return get_product_entry_mode(product_type) == "catalog"


def get_catalog_tab(product_type: str) -> Optional[str]:
    """Return the GSheets tab name for a catalog-supported product type."""
    pt = normalize_product_type(product_type)
    return _CANONICAL_TO_TAB.get(pt)


# ── Catalog lookup from df_long ──────────────────────────────────────────────

def get_catalog_managers(df_long: pd.DataFrame) -> list[str]:
    """Return sorted list of manager names from the current df_long."""
    if df_long is None or df_long.empty or "manager" not in df_long.columns:
        return []
    managers = sorted(df_long["manager"].dropna().unique().tolist())
    return [m for m in managers if str(m).strip()]


def get_catalog_funds(df_long: pd.DataFrame, manager: str) -> list[str]:
    """Return sorted fund names for a given manager."""
    if df_long is None or df_long.empty or not manager:
        return []
    sub = df_long[df_long["manager"] == manager]
    if "fund" not in sub.columns:
        return []
    funds = sorted(sub["fund"].dropna().unique().tolist())
    return [f for f in funds if str(f).strip()]


def get_catalog_tracks(df_long: pd.DataFrame, manager: str, fund: str = "") -> list[str]:
    """Return sorted track names for a given manager (and optionally fund)."""
    if df_long is None or df_long.empty or not manager:
        return []
    sub = df_long[df_long["manager"] == manager]
    if fund and "fund" in sub.columns:
        by_fund = sub[sub["fund"] == fund]
        if not by_fund.empty:
            sub = by_fund
    if "track" not in sub.columns:
        return []
    tracks = sorted(sub["track"].dropna().unique().tolist())
    return [t for t in tracks if str(t).strip()]


def get_catalog_preview(
    df_long: pd.DataFrame,
    manager: str,
    fund: str = "",
    track: str = "",
) -> Optional[dict]:
    """
    Return allocation preview dict for a catalog selection.
    Returns None if nothing matched.
    Keys: equity_pct, foreign_pct, fx_pct, illiquid_pct, sharpe, matched_by
    """
    if df_long is None or df_long.empty or not manager:
        return None

    sub = df_long.copy()

    # Filter by manager
    sub = sub[sub["manager"] == manager]
    if sub.empty:
        return None

    # Filter by fund if provided
    if fund and "fund" in sub.columns:
        by_fund = sub[sub["fund"] == fund]
        if not by_fund.empty:
            sub = by_fund
            matched_by = "fund"
        else:
            matched_by = "manager"
    else:
        matched_by = "manager"

    # Filter by track if provided
    if track and "track" in sub.columns:
        by_track = sub[sub["track"] == track]
        if not by_track.empty:
            sub = by_track

    row = sub.iloc[0]

    def _f(col: str) -> Optional[float]:
        v = row.get(col)
        if v is None: return None
        try:
            fv = float(v)
            return None if math.isnan(fv) else fv
        except (ValueError, TypeError):
            return None

    COL_MAP = {
        "equity_pct":   "stocks",
        "foreign_pct":  "foreign",
        "fx_pct":       "fx",
        "illiquid_pct": "illiquid",
    }
    result = {pf_col: _f(app_col) for pf_col, app_col in COL_MAP.items()}
    result["sharpe"]     = _f("sharpe")
    result["matched_by"] = matched_by
    result["fund_name"]  = str(row.get("fund", fund)).strip()
    result["track_name"] = str(row.get("track", track)).strip()

    # Only return if at least one allocation field is non-None
    if any(v is not None for k, v in result.items() if k not in ("matched_by","fund_name","track_name")):
        return result
    return None
