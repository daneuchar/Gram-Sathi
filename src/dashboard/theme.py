"""Shared Figma design tokens and CSS for Gram Saathi dashboard."""

PRIMARY = "#2338E0"
PRIMARY_LIGHT = "#EEF0FD"
BG = "#F8F9FB"
CARD_BG = "#FFFFFF"
BORDER = "#E5E7EB"
TEXT = "#111827"
TEXT_MUTED = "#6B7280"
GREEN = "#16A34A"
GREEN_BG = "#DCFCE7"
ORANGE = "#D97706"
ORANGE_BG = "#FEF3C7"
RED = "#DC2626"
RED_BG = "#FEE2E2"

GLOBAL_CSS = f"""
<style>
/* ── Page background ── */
.stApp {{ background-color: {BG}; }}
section[data-testid="stSidebar"] {{ background-color: {CARD_BG}; border-right: 1px solid {BORDER}; }}
section[data-testid="stSidebar"] .stRadio label {{ color: {TEXT_MUTED}; font-size: 13px; padding: 6px 0; }}
section[data-testid="stSidebar"] .stRadio label:hover {{ color: {TEXT}; }}

/* ── Hide default streamlit chrome ── */
#MainMenu, footer {{ visibility: hidden; }}
header {{ visibility: visible; }}
.block-container {{ padding-top: 1.5rem; padding-bottom: 2rem; max-width: 100%; }}

/* ── Keep sidebar always visible ── */
section[data-testid="stSidebar"] {{ min-width: 220px !important; width: 220px !important; }}
section[data-testid="stSidebar"] > div {{ padding-top: 1rem; }}

/* ── Stat card ── */
.gs-card {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 0;
}}
.gs-card-label {{ font-size: 13px; color: {TEXT_MUTED}; font-weight: 500; margin-bottom: 4px; }}
.gs-card-value {{ font-size: 32px; font-weight: 700; color: {TEXT}; line-height: 1.1; margin: 4px 0; }}
.gs-card-sub {{ font-size: 12px; color: {TEXT_MUTED}; margin-top: 4px; }}
.gs-card-sub.green {{ color: {GREEN}; }}
.gs-card-sub.orange {{ color: {ORANGE}; }}

/* ── Section card ── */
.gs-section {{
    background: {CARD_BG};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 20px 24px;
    margin-bottom: 16px;
}}
.gs-section-title {{ font-size: 14px; font-weight: 600; color: {TEXT}; margin-bottom: 16px; }}

/* ── Page title ── */
.gs-page-title {{ font-size: 24px; font-weight: 700; color: {TEXT}; margin-bottom: 20px; }}
.gs-page-subtitle {{ font-size: 13px; color: {TEXT_MUTED}; margin-top: -16px; margin-bottom: 20px; }}

/* ── Badge ── */
.gs-badge {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 99px;
    font-size: 12px;
    font-weight: 600;
}}
.gs-badge.green {{ background: {GREEN_BG}; color: {GREEN}; }}
.gs-badge.orange {{ background: {ORANGE_BG}; color: {ORANGE}; }}
.gs-badge.red {{ background: {RED_BG}; color: {RED}; }}
.gs-badge.blue {{ background: {PRIMARY_LIGHT}; color: {PRIMARY}; }}

/* ── Tag ── */
.gs-tag {{
    display: inline-block;
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    color: {TEXT_MUTED};
    margin-right: 4px;
}}

/* ── Alert row ── */
.gs-alert-row {{ display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid {BG}; font-size: 13px; color: {TEXT}; }}
.gs-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
.gs-dot.red {{ background: {RED}; }}
.gs-dot.orange {{ background: {ORANGE}; }}
.gs-dot.green {{ background: {GREEN}; }}

/* ── Live call card ── */
.gs-call-card {{ background: {CARD_BG}; border: 1px solid {BORDER}; border-radius: 10px; padding: 16px 20px; margin-bottom: 12px; border-left: 4px solid {PRIMARY}; }}
.gs-call-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
.gs-call-phone {{ font-size: 15px; font-weight: 600; color: {TEXT}; }}
.gs-call-meta {{ font-size: 12px; color: {TEXT_MUTED}; margin-bottom: 12px; }}
.gs-chat-you {{ font-size: 13px; color: {TEXT}; margin: 6px 0; }}
.gs-chat-bot {{ font-size: 13px; color: {PRIMARY}; margin: 6px 0; }}
.gs-call-duration {{ font-size: 13px; font-weight: 600; color: {GREEN}; }}

/* ── Table styling ── */
.gs-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
.gs-table th {{ text-align: left; padding: 10px 16px; color: {TEXT_MUTED}; font-weight: 500; font-size: 12px; border-bottom: 1px solid {BORDER}; }}
.gs-table td {{ padding: 14px 16px; border-bottom: 1px solid {BG}; color: {TEXT}; }}
.gs-table tr:hover td {{ background: {BG}; }}

/* ── Progress bar ── */
.gs-progress-wrap {{ background: {BORDER}; border-radius: 99px; height: 6px; margin: 4px 0; }}
.gs-progress-bar {{ height: 6px; border-radius: 99px; background: {PRIMARY}; }}
.gs-progress-bar.green {{ background: {GREEN}; }}

/* ── Health row ── */
.gs-health-row {{ display: flex; align-items: center; padding: 14px 16px; border-bottom: 1px solid {BG}; font-size: 13px; }}
.gs-health-service {{ flex: 2; font-weight: 500; color: {TEXT}; }}
.gs-health-status {{ flex: 1; }}
.gs-health-metric {{ flex: 3; color: {TEXT_MUTED}; }}

/* ── Error count badge ── */
.gs-err-count {{
    display: inline-block;
    min-width: 28px;
    text-align: center;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 13px;
    font-weight: 700;
}}
.gs-err-count.zero {{ background: #F0FDF4; color: {GREEN}; }}
.gs-err-count.nonzero {{ background: {RED_BG}; color: {RED}; }}

/* ── Topbar ── */
.gs-topbar {{ display: flex; justify-content: space-between; align-items: center; padding: 0 0 20px 0; }}
.gs-active-pill {{ background: {GREEN_BG}; color: {GREEN}; border-radius: 99px; padding: 5px 14px; font-size: 13px; font-weight: 600; }}

/* ── Empty state ── */
.gs-empty {{ text-align: center; color: {TEXT_MUTED}; padding: 40px; font-size: 13px; border: 1px dashed {BORDER}; border-radius: 10px; }}
</style>
"""


def stat_card(label: str, value: str, sub: str = "", sub_class: str = "") -> str:
    sub_html = f'<div class="gs-card-sub {sub_class}">{sub}</div>' if sub else ""
    return f"""
    <div class="gs-card">
        <div class="gs-card-label">{label}</div>
        <div class="gs-card-value">{value}</div>
        {sub_html}
    </div>"""


def section(title: str, body: str) -> str:
    return f"""
    <div class="gs-section">
        <div class="gs-section-title">{title}</div>
        {body}
    </div>"""


def badge(text: str, color: str = "blue") -> str:
    return f'<span class="gs-badge {color}">{text}</span>'


def tag(text: str) -> str:
    return f'<span class="gs-tag">{text}</span>'
