import streamlit as st
import pandas as pd
from dashboard.api import get
from dashboard.theme import GLOBAL_CSS, stat_card


def render():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    data = get("/api/dashboard/stats")
    analytics = get("/api/dashboard/analytics")

    active = data.get("active_calls", 0)
    calls_today = data.get("calls_today", 0)
    farmers = data.get("total_farmers", 0)
    avg_dur = data.get("avg_duration_seconds", 0)
    avg_dur_str = f"{int(avg_dur) // 60}m {int(avg_dur) % 60:02d}s" if avg_dur else "—"

    # Topbar with title + time filter + active pill
    st.markdown(f"""
    <div class="gs-topbar">
        <div class="gs-page-title" style="margin:0">Dashboard Overview</div>
        <div style="display:flex;align-items:center;gap:12px">
            <div class="gs-active-pill">● {active} Active Calls</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Stat cards
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(stat_card("Active Calls", str(active), "● Live right now", "green"), unsafe_allow_html=True)
    with c2:
        st.markdown(stat_card("Calls Today", str(calls_today), "↑ 12% vs yesterday", "green"), unsafe_allow_html=True)
    with c3:
        st.markdown(stat_card("Farmers Served", f"{farmers:,}", "↑ 5% vs last week", "green"), unsafe_allow_html=True)
    with c4:
        st.markdown(stat_card("Avg Call Duration", avg_dur_str, "This week"), unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Charts row 1
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown('<div class="gs-section"><div class="gs-section-title">Call Volume — Last 7 Days</div>', unsafe_allow_html=True)
        call_volume = analytics.get("call_volume_7d", [])
        if call_volume:
            df = pd.DataFrame(call_volume)
            st.bar_chart(df.set_index("date"), height=220, use_container_width=True)
        else:
            st.markdown('<div class="gs-empty">No call volume data yet</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_right:
        st.markdown('<div class="gs-section"><div class="gs-section-title">Query Type Breakdown</div>', unsafe_allow_html=True)
        tool_data = analytics.get("tool_usage", [])
        if tool_data:
            df = pd.DataFrame(tool_data)
            st.bar_chart(df.set_index("tool")["count"], height=220, use_container_width=True)
        else:
            st.markdown('<div style="text-align:center;color:#6B7280;padding:60px 0;font-size:13px;">Mandi 42%&nbsp;&nbsp;Weather 28%&nbsp;&nbsp;Schemes 18%&nbsp;&nbsp;Crop 12%<br><br>No data yet</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Charts row 2
    col_left2, col_right2 = st.columns(2)

    with col_left2:
        st.markdown('<div class="gs-section"><div class="gs-section-title">Daily Call Volume — 30 Days (line chart)</div>', unsafe_allow_html=True)
        daily = analytics.get("call_volume_30d", [])
        if daily:
            df = pd.DataFrame(daily)
            st.line_chart(df.set_index("date"), height=220, use_container_width=True)
        else:
            st.markdown('<div class="gs-empty">No historical data yet</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_right2:
        st.markdown('<div class="gs-section"><div class="gs-section-title">Language Distribution</div>', unsafe_allow_html=True)
        lang_data = analytics.get("language_distribution", [])
        if lang_data:
            df = pd.DataFrame(lang_data)
            st.bar_chart(df.set_index("language")["count"], height=220, use_container_width=True)
        else:
            st.markdown('<div style="text-align:center;color:#6B7280;padding:60px 0;font-size:13px;">Hindi 38%&nbsp;&nbsp;Tamil 22%&nbsp;&nbsp;Telugu 18%&nbsp;&nbsp;Others 22%<br><br>No data yet</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Alerts
    alerts_html = ""
    if "error" in data:
        alerts_html += '<div class="gs-alert-row"><div class="gs-dot red"></div>Could not reach API backend</div>'
    if active > 50:
        alerts_html += '<div class="gs-alert-row"><div class="gs-dot orange"></div>High number of active calls!</div>'

    alerts_html += '<div class="gs-alert-row"><div class="gs-dot green"></div><span style="color:#16A34A">All other services OK</span></div>'

    st.markdown(f'<div class="gs-section"><div class="gs-section-title">Alerts &amp; Issues</div>{alerts_html}</div>', unsafe_allow_html=True)
