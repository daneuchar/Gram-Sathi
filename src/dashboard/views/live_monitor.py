import time
import streamlit as st
from dashboard.api import get
from dashboard.theme import GLOBAL_CSS
from dashboard.config import POLL_INTERVAL_SECONDS


def _mask_phone(phone: str) -> str:
    if len(phone) >= 10:
        return phone[:5] + "XX XXXXX" + phone[-2:]
    return phone


def render():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    data = get("/api/dashboard/calls", params={"status": "in-progress", "per_page": 50})
    calls = data.get("calls", []) if "error" not in data else []

    active_count = len(calls)

    st.markdown(f"""
    <div class="gs-topbar">
        <div>
            <div class="gs-page-title">Active Calls</div>
            <div class="gs-page-subtitle">Real-time call feed — auto-updates via WebSocket</div>
        </div>
        <div class="gs-active-pill">● {active_count} Active Calls</div>
    </div>
    """, unsafe_allow_html=True)

    if not calls:
        st.markdown('<div class="gs-empty">No active calls right now — waiting for new connections...</div>', unsafe_allow_html=True)
    else:
        for call in calls:
            phone = _mask_phone(call.get("phone", "Unknown"))
            lang = call.get("language_detected", "Unknown")
            dur = call.get("duration_seconds", 0) or 0
            dur_str = f"{dur // 60}m {dur % 60:02d}s"
            state = call.get("state", "")
            district = call.get("district", "")
            location = f"{state}" if state else "Unknown"

            st.markdown(f"""
            <div class="gs-call-card">
                <div class="gs-call-header">
                    <div>
                        <span class="gs-call-phone">● +91 {phone}</span>
                        <span style="margin-left:10px;font-size:13px;font-weight:500;color:#374151">{lang}</span>
                    </div>
                    <div>
                        <span class="gs-call-duration">{dur_str}</span>
                        <span style="margin-left:16px;font-size:12px;color:#6B7280">{location}</span>
                    </div>
                </div>
                <div class="gs-call-meta">Duration: {dur_str} &nbsp;|&nbsp; {lang} &nbsp;|&nbsp; {location}</div>
                <div class="gs-chat-bot" style="font-style:italic;color:#6B7280;font-size:12px;margin-top:8px">Bot is responding...</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown('<div style="height:12px"></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="gs-empty" style="border:none;padding:16px;color:#9CA3AF">No more active calls — waiting for new connections...</div>', unsafe_allow_html=True)

    time.sleep(POLL_INTERVAL_SECONDS)
    st.rerun()
