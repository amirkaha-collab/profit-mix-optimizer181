# -*- coding: utf-8 -*-
"""
app_shell/home.py -- Phase 2
Two-mode home + research workbench.
"""
from __future__ import annotations
import streamlit as st

_HOME_CSS = """
<style>
.mode-grid{display:grid;grid-template-columns:1fr 1fr;gap:22px;direction:rtl}
.mc{border-radius:18px;padding:36px 32px 28px;position:relative;overflow:hidden;
    transition:transform .2s,box-shadow .2s}
.mc:hover{transform:translateY(-4px)}
.mc-c{background:linear-gradient(155deg,#0b1f42 0%,#0f2d5e 55%,#1a4a9c 100%);
  box-shadow:0 8px 32px rgba(11,31,66,.4)}
.mc-c:hover{box-shadow:0 16px 48px rgba(11,31,66,.5)}
.mc-r{background:#ffffff;border:1.5px solid #e2e8f0;
  box-shadow:0 4px 16px rgba(15,23,42,.06)}
.mc-r:hover{box-shadow:0 12px 32px rgba(15,23,42,.11);border-color:#93c5fd}
.mc-tag{display:inline-flex;align-items:center;gap:5px;font-size:9px;font-weight:800;
  letter-spacing:2px;text-transform:uppercase;padding:3px 10px;border-radius:999px;margin-bottom:20px}
.mc-tag-c{background:rgba(255,255,255,.14);color:rgba(255,255,255,.82)}
.mc-tag-r{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}
.mc-ico{font-size:42px;margin-bottom:16px;display:block;line-height:1}
.mc-tc{font-size:27px;font-weight:900;color:#fff;letter-spacing:-.7px;margin:0 0 10px}
.mc-tr{font-size:27px;font-weight:900;color:#0b1929;letter-spacing:-.7px;margin:0 0 10px}
.mc-dc{font-size:13px;color:rgba(186,214,254,.78);line-height:1.7}
.mc-dr{font-size:13px;color:#475569;line-height:1.7}
.mc-steps{margin-top:22px;padding-top:16px;direction:rtl}
.mc-sc{border-top:1px solid rgba(255,255,255,.1)}
.mc-sr{border-top:1px solid #f1f5f9}
.mc-step{display:flex;align-items:center;gap:8px;margin-bottom:7px}
.mc-sn{width:19px;height:19px;border-radius:50%;font-size:9.5px;font-weight:800;
  display:flex;align-items:center;justify-content:center;flex-shrink:0}
.mc-sn-c{background:rgba(255,255,255,.18);color:#fff}
.mc-sn-r{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}
.mc-sl-c{font-size:11.5px;color:rgba(255,255,255,.76);font-weight:500}
.mc-sl-r{font-size:11.5px;color:#475569;font-weight:500}

/* mode badge */
.mode-badge{display:inline-flex;align-items:center;gap:5px;font-size:11px;
  font-weight:700;padding:4px 12px;border-radius:999px}
.mode-badge-c{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}
.mode-badge-r{background:#f5f3ff;color:#5b21b6;border:1px solid #ddd6fe}

/* research workbench */
.rb-card{background:#fff;border:1.5px solid #e2e8f0;border-radius:16px;
  padding:20px 18px 16px;direction:rtl;text-align:right;
  transition:transform .18s,box-shadow .18s,border-color .18s}
.rb-card:hover{transform:translateY(-3px);
  box-shadow:0 8px 24px rgba(15,23,42,.09);border-color:#93c5fd}
.rb-ico{font-size:28px;margin-bottom:10px;display:block;line-height:1}
.rb-title{font-size:14px;font-weight:900;color:#0b1929;margin-bottom:5px}
.rb-desc{font-size:11.5px;color:#64748b;line-height:1.6}
</style>
"""

_DISC = """<div style="background:#fffceb;border:1px solid #fde68a;
  border-right:3px solid #f59e0b;border-radius:10px;padding:9px 16px;
  direction:rtl;text-align:right;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
  <span style="font-size:10.5px;font-weight:700;color:#92400e">⚠️ גרסת בטא</span>
  <div style="display:flex;gap:5px;flex-wrap:wrap">
    <span style="font-size:9.5px;color:#78350f;padding:2px 8px;border-radius:999px;
      background:rgba(245,158,11,.07);border:1px solid rgba(245,158,11,.18)">ייתכנו שגיאות חישוב</span>
    <span style="font-size:9.5px;color:#78350f;padding:2px 8px;border-radius:999px;
      background:rgba(245,158,11,.07);border:1px solid rgba(245,158,11,.18)">לא ייעוץ פיננסי</span>
    <span style="font-size:9.5px;color:#78350f;padding:2px 8px;border-radius:999px;
      background:rgba(245,158,11,.07);border:1px solid rgba(245,158,11,.18)">יש לאמת מול מקורות רשמיים</span>
  </div>
</div>"""


def inject_css():
    st.markdown(_HOME_CSS, unsafe_allow_html=True)


def render_home(nav_to_fn) -> None:
    """Two-mode selection screen."""
    st.markdown("""
<div style="padding:36px 0 12px;direction:rtl;text-align:right">
  <div style="font-size:10px;font-weight:800;letter-spacing:2.5px;color:#2563eb;
       text-transform:uppercase;margin-bottom:8px">בחר מצב עבודה</div>
  <div style="font-size:34px;font-weight:900;color:#0b1929;letter-spacing:-1px;margin:0">
    איך תרצה לעבוד?
  </div>
</div>""", unsafe_allow_html=True)

    cl, cr = st.columns(2, gap="large")

    with cl:
        st.markdown("""
<div class="mc mc-c" dir="rtl">
  <div class="mc-tag mc-tag-c">&#x1F464; מסלול מובנה</div>
  <span class="mc-ico">👤</span>
  <div class="mc-tc">עבודה עם לקוח</div>
  <div class="mc-dc">מסלול מודרך: קליטת נתונים, ניתוח, אופטימיזציה, הסברי AI והכנת חבילת מצגת ללקוח.</div>
  <div class="mc-steps mc-sc">
    <div class="mc-step"><span class="mc-sn mc-sn-c">1</span><span class="mc-sl-c">קליטת נתונים ותיק קיים</span></div>
    <div class="mc-step"><span class="mc-sn mc-sn-c">2</span><span class="mc-sl-c">תמונת מצב משוקללת</span></div>
    <div class="mc-step"><span class="mc-sn mc-sn-c">3</span><span class="mc-sl-c">תכנון ואופטימיזציה</span></div>
    <div class="mc-step"><span class="mc-sn mc-sn-c">4</span><span class="mc-sl-c">הסברי AI ואישור</span></div>
    <div class="mc-step"><span class="mc-sn mc-sn-c">5</span><span class="mc-sl-c">חבילת דו"ח ומצגת</span></div>
  </div>
</div>""", unsafe_allow_html=True)
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        if st.button("👤 התחל עבודה עם לקוח", key="hp_client",
                     use_container_width=True, type="primary"):
            st.session_state["app_mode"] = "client"
            st.session_state["app_page"] = "client"
            st.session_state["client_wizard_step"] = 1
            st.rerun()

    with cr:
        st.markdown("""
<div class="mc mc-r" dir="rtl">
  <div class="mc-tag mc-tag-r">🔭 מצב חופשי</div>
  <span class="mc-ico">🔭</span>
  <div class="mc-tr">מחקר וכלי עבודה</div>
  <div class="mc-dr">גישה ישירה לניתוחי מוסדיים, בניית תמהילים, ניתוח תיק קיים, השוואות וסימולציות.</div>
  <div class="mc-steps mc-sr">
    <div class="mc-step"><span class="mc-sn mc-sn-r">→</span><span class="mc-sl-r">בניית תמהיל למוצר</span></div>
    <div class="mc-step"><span class="mc-sn mc-sn-r">→</span><span class="mc-sl-r">ניתוח אסטרטגיות מוסדיות</span></div>
    <div class="mc-step"><span class="mc-sn mc-sn-r">→</span><span class="mc-sl-r">ניתוח תיק לקוח standalone</span></div>
    <div class="mc-step"><span class="mc-sn mc-sn-r">→</span><span class="mc-sl-r">השוואת מסלולים וסימולציות</span></div>
  </div>
</div>""", unsafe_allow_html=True)
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        if st.button("🔭 כנס למצב מחקר", key="hp_research",
                     use_container_width=True, type="secondary"):
            st.session_state["app_mode"] = "research"
            st.session_state["app_page"] = "research"
            st.rerun()

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    st.markdown(_DISC, unsafe_allow_html=True)


def render_research_workbench(nav_to_fn) -> None:
    """Research mode — 2-column card grid. ISA routes to dedicated screen."""
    st.markdown("""
<div style="direction:rtl;text-align:right;padding:8px 0 18px">
  <div style="font-size:10px;font-weight:800;letter-spacing:2.5px;color:#2563eb;
       text-transform:uppercase;margin-bottom:6px">&#x1F52D; מצב מחקר</div>
  <div style="font-size:24px;font-weight:900;color:#0b1929;margin-bottom:4px">כלים לניתוח חופשי</div>
  <div style="font-size:13px;color:#475569">בחר כלי ועולם מוצר — גישה ישירה, ללא סדר מחייב</div>
</div>""", unsafe_allow_html=True)

    col_mix, col_isa = st.columns(2, gap="large")

    with col_mix:
        st.markdown("""
<div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:16px;
     padding:22px 20px 14px;direction:rtl;text-align:right">
  <div style="font-size:28px;margin-bottom:8px">&#x1F3E6;</div>
  <div style="font-size:15px;font-weight:900;color:#0b1929;margin-bottom:6px">בניית תמהיל</div>
  <div style="font-size:12px;color:#64748b;line-height:1.6;margin-bottom:12px">
    הגדר יעדי חשיפה וקבל חלופות אופטימליות לפי עולם מוצר
  </div>
</div>""", unsafe_allow_html=True)
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        mx_c = st.columns(5, gap="small")
        for col, (w, k) in zip(mx_c, [
            ("קרנות השתלמות","rb_ht"),("קופות גמל","rb_gm"),
            ("פוליסות חיסכון","rb_pl"),("קרנות פנסיה","rb_pn"),("גמל להשקעה","rb_gi"),
        ]):
            with col:
                if st.button(w.replace("קרנות ","").replace("קופות ",""),
                             key=k, use_container_width=True, type="secondary"):
                    nav_to_fn("app", w)
                    st.rerun()

    with col_isa:
        st.markdown("""
<div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:16px;
     padding:22px 20px 14px;direction:rtl;text-align:right">
  <div style="font-size:28px;margin-bottom:8px">&#x1F4D0;</div>
  <div style="font-size:15px;font-weight:900;color:#0b1929;margin-bottom:6px">ניתוח אסטרטגיות מוסדיים</div>
  <div style="font-size:12px;color:#64748b;line-height:1.6;margin-bottom:12px">
    ניתוח אלוקציות היסטוריות של גופים מובילים — נפתח במסך ייעודי
  </div>
</div>""", unsafe_allow_html=True)
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
        isa_c = st.columns(5, gap="small")
        for col, (w, k) in zip(isa_c, [
            ("קרנות השתלמות","ri_ht"),("קופות גמל","ri_gm"),
            ("פוליסות חיסכון","ri_pl"),("קרנות פנסיה","ri_pn"),("גמל להשקעה","ri_gi"),
        ]):
            with col:
                if st.button(w.replace("קרנות ","").replace("קופות ",""),
                             key=k, use_container_width=True, type="secondary"):
                    st.session_state["app_page"]           = "isa_research"
                    st.session_state["isa_research_product"] = w
                    st.session_state["product_type"]        = w
                    st.rerun()

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    st.markdown(_DISC, unsafe_allow_html=True)


def _mode_header(mode_lbl: str, title: str, sub: str) -> None:
    st.markdown(f"""
<div style="background:linear-gradient(135deg,#f8fafc,#f0f4ff);border:1px solid #dde6f2;
     border-radius:14px;padding:18px 22px;direction:rtl;text-align:right;margin-bottom:20px">
  <div style="font-size:9.5px;font-weight:800;letter-spacing:2px;color:#2563eb;
       text-transform:uppercase;margin-bottom:5px">{mode_lbl}</div>
  <div style="font-size:20px;font-weight:900;color:#0b1929;margin-bottom:3px">{title}</div>
  <div style="font-size:13px;color:#475569">{sub}</div>
</div>""", unsafe_allow_html=True)


def render_mode_badge_back_btn() -> None:
    """Back-to-home + mode context shown on all non-home screens."""
    bk, mb, sp = st.columns([1, 1.8, 7.2])
    with bk:
        if st.button("← בית", key="btn_back_home_shell"):
            st.session_state["app_page"] = "home"
            st.session_state["app_mode"] = "home"
            st.rerun()
    with mb:
        m = st.session_state.get("app_mode","")
        if m == "client":
            st.markdown('<div class="mode-badge mode-badge-c">👤 מצב לקוח</div>',
                        unsafe_allow_html=True)
        elif m == "research":
            st.markdown('<div class="mode-badge mode-badge-r">🔭 מחקר</div>',
                        unsafe_allow_html=True)


def render_isa_research_screen(df_long, nav_to_fn) -> None:
    """
    Dedicated Institutional Strategy Analysis screen for Research Mode.
    Opens directly from the research workbench tile — no generic product page.
    Reuses existing render_institutional_analysis engine.
    """
    product_type = st.session_state.get("isa_research_product", "קרנות השתלמות")

    # ── Back button ─────────────────────────────────────────────────────────
    b1, b2, _ = st.columns([1, 1.4, 7.6])
    with b1:
        if st.button("← חזרה", key="isa_back_btn"):
            st.session_state["app_page"] = "research"
            st.rerun()
    with b2:
        st.markdown('<span style="font-size:11px;font-weight:700;color:#5b21b6;'
                    'background:#f5f3ff;border:1px solid #ddd6fe;border-radius:999px;'
                    'padding:4px 12px">🔭 מחקר מוסדי</span>',
                    unsafe_allow_html=True)

    # ── Header ─────────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="background:linear-gradient(135deg,#0b1f42,#0f2d5e);'
        f'border-radius:12px;padding:14px 20px;direction:rtl;text-align:right;'
        f'margin-bottom:16px">'
        f'<div style="font-size:9.5px;font-weight:800;letter-spacing:2px;'
        f'text-transform:uppercase;color:rgba(96,165,250,.7);margin-bottom:3px">'
        f'📐 ניתוח אסטרטגיות מוסדיים</div>'
        f'<div style="font-size:19px;font-weight:900;color:#fff">{product_type}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Product type switcher ───────────────────────────────────────────────
    WORLDS = ["קרנות השתלמות", "פוליסות חיסכון", "קרנות פנסיה", "קופות גמל", "גמל להשקעה"]
    cols = st.columns(len(WORLDS), gap="small")
    for col, w in zip(cols, WORLDS):
        with col:
            if st.button(
                w.replace("קרנות ", "").replace("קופות ", ""),
                key=f"isa_sw_{w}",
                use_container_width=True,
                type="primary" if w == product_type else "secondary",
            ):
                st.session_state["isa_research_product"] = w
                st.session_state["product_type"] = w
                st.rerun()

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # ── Existing ISA engine — no expander since this IS the dedicated screen ─
    try:
        from institutional_strategy_analysis.ui import render_institutional_analysis
        render_institutional_analysis(
            product_type      = product_type,
            df_long           = df_long,
            selected_managers = st.session_state.get("selected_managers"),
            expanded          = True,
            use_expander      = False,   # dedicated screen: no wrapper expander
        )
    except Exception as e:
        import traceback
        st.error(f"שגיאת ניתוח: {e}")
        st.code(traceback.format_exc())
