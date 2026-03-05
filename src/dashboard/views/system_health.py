import time
from datetime import datetime
import streamlit as st
from dashboard.theme import GLOBAL_CSS

GREEN = "#16A34A"
ORANGE = "#D97706"
RED = "#DC2626"

SERVICES = [
    ("FastAPI Backend", "healthy", "99.8% uptime"),
    ("Amazon Bedrock (Claude)", "healthy", "avg latency: 890ms"),
    ("Amazon Q Business", "healthy", "avg latency: 1.1s"),
    ("Exotel Telephony", "degraded", "2 failed webhooks in last hour"),
    ("PostgreSQL", "healthy", "avg latency: 12ms"),
    ("Redis Cache", "healthy", "avg latency: 3ms"),
    ("data.gov.in API", "healthy", "avg latency: 410ms"),
    ("IndianAPI.in (Weather)", "healthy", "avg latency: 380ms"),
]

ERROR_COUNTS = [
    ("Failed callbacks", 2),
    ("ASR errors", 0),
    ("LLM errors", 1),
    ("TTS errors", 0),
    ("Tool call errors", 3),
]

CACHE_ITEMS = [
    ("Mandi Prices (30-min TTL)", 78),
    ("Weather (2-hour TTL)", 91),
    ("Session Data", 95),
]


def _status_dot(status: str) -> str:
    color = GREEN if status == "healthy" else (ORANGE if status == "degraded" else RED)
    return f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{color};margin-right:10px;flex-shrink:0"></span>'


def _status_label(status: str) -> str:
    color = GREEN if status == "healthy" else (ORANGE if status == "degraded" else RED)
    label = status.capitalize()
    return f'<span style="color:{color};font-weight:600;font-size:13px">{label}</span>'


def _err_badge(count: int) -> str:
    if count == 0:
        return f'<span class="gs-err-count zero">{count}</span>'
    return f'<span class="gs-err-count nonzero">{count}</span>'


def render():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    now = datetime.now().strftime("%H:%M:%S")

    # Topbar
    col_title, col_refresh = st.columns([6, 2])
    col_title.markdown("""
    <div class="gs-page-title" style="margin-bottom:4px">System Health</div>
    <div class="gs-page-subtitle">Auto-refreshes every 10 seconds</div>
    """, unsafe_allow_html=True)
    with col_refresh:
        st.markdown(f"<div style='text-align:right;font-size:12px;color:#9CA3AF;padding:4px 0'>Last updated: {now}</div>", unsafe_allow_html=True)
        if st.button("↻  Refresh now", use_container_width=True):
            st.rerun()

    # Service table
    rows = ""
    for name, status, metric in SERVICES:
        dot = _status_dot(status)
        lbl = _status_label(status)
        rows += f"""
        <tr>
            <td style="padding:14px 20px;font-weight:500;color:#111827;border-bottom:1px solid #F9FAFB;width:40%"><div style="display:flex;align-items:center">{dot}{name}</div></td>
            <td style="padding:14px 20px;border-bottom:1px solid #F9FAFB;width:20%">{lbl}</td>
            <td style="padding:14px 20px;color:#6B7280;border-bottom:1px solid #F9FAFB">{metric}</td>
        </tr>"""

    st.markdown(f"""
    <div class="gs-section" style="padding:0">
        <table style="width:100%;border-collapse:collapse;font-size:13px">
            <thead>
                <tr style="border-bottom:1px solid #E5E7EB">
                    <th style="padding:14px 20px;text-align:left;color:#6B7280;font-weight:500;font-size:12px;width:40%">Service</th>
                    <th style="padding:14px 20px;text-align:left;color:#6B7280;font-weight:500;font-size:12px;width:20%">Status</th>
                    <th style="padding:14px 20px;text-align:left;color:#6B7280;font-weight:500;font-size:12px">Key Metric</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

    # Bottom row: 3 panels
    c1, c2, c3 = st.columns([2, 1.5, 1.5])

    with c1:
        st.markdown("""
        <div class="gs-section">
            <div class="gs-section-title">End-to-End Latency &nbsp;<span style="font-weight:400;color:#6B7280">(last 1 hour)</span></div>
            <div style="background:#F3F4F6;border-radius:8px;height:140px;display:flex;align-items:center;justify-content:center;color:#9CA3AF;font-size:12px">
                [ Latency line chart — target line at 1.5s ]
            </div>
            <div style="margin-top:10px;font-size:12px;color:#16A34A">
                Current avg: 1.1s &nbsp;&nbsp; Target: &lt; 1.5s &nbsp;&nbsp; Status: OK
            </div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        err_rows = "".join(
            f'<div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #F3F4F6">'
            f'<span style="font-size:13px;color:#374151">{label}</span>{_err_badge(count)}</div>'
            for label, count in ERROR_COUNTS
        )
        st.markdown(f"""
        <div class="gs-section">
            <div class="gs-section-title">Error Rate — Last 24h</div>
            {err_rows}
        </div>
        """, unsafe_allow_html=True)

    with c3:
        cache_rows = ""
        for label, pct in CACHE_ITEMS:
            bar_color = GREEN if pct >= 80 else "#2338E0"
            cache_rows += f"""
            <div style="margin-bottom:14px">
                <div style="font-size:13px;color:#374151;margin-bottom:4px">{label}</div>
                <div style="display:flex;align-items:center;gap:8px">
                    <div class="gs-progress-wrap" style="flex:1"><div class="gs-progress-bar" style="width:{pct}%;background:{bar_color}"></div></div>
                    <span style="font-size:12px;color:#6B7280;min-width:32px">{pct}%</span>
                </div>
            </div>"""
        st.markdown(f"""
        <div class="gs-section">
            <div class="gs-section-title">Cache Hit Rate</div>
            {cache_rows}
        </div>
        """, unsafe_allow_html=True)

    time.sleep(10)
    st.rerun()
