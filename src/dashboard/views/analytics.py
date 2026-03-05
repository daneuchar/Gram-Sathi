import streamlit as st
import pandas as pd
from dashboard.api import get
from dashboard.theme import GLOBAL_CSS, stat_card


def render():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    data = get("/api/dashboard/analytics")
    stats = get("/api/dashboard/stats")

    # Topbar
    t1, t2 = st.columns([6, 2])
    t1.markdown('<div class="gs-page-title">Analytics</div>', unsafe_allow_html=True)
    with t2:
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        btn_cols = st.columns([1, 1, 1, 2])
        btn_cols[0].button("Today", use_container_width=True)
        btn_cols[1].button("This Week", use_container_width=True)
        btn_cols[2].button("This Month", type="primary", use_container_width=True)
        with btn_cols[3]:
            st.markdown(
                '<a href="#" style="display:block;background:#2338E0;color:#fff;border-radius:8px;padding:8px 16px;font-size:13px;font-weight:600;text-align:center;text-decoration:none">Export CSV ↓</a>',
                unsafe_allow_html=True,
            )

    # Stat cards
    total_calls = data.get("total_calls_month", 0)
    avg_dur = stats.get("avg_duration_seconds", 0)
    avg_dur_str = f"{int(avg_dur) // 60}m {int(avg_dur) % 60:02d}s" if avg_dur else "—"
    lang_active = data.get("languages_active", 0)
    new_farmers = data.get("new_farmers_month", 0)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(stat_card("Total Calls (Month)", f"{total_calls:,}", "Mar 2026"), unsafe_allow_html=True)
    with c2:
        st.markdown(stat_card("Avg Call Duration", avg_dur_str, "Mar 2026"), unsafe_allow_html=True)
    with c3:
        st.markdown(stat_card("Languages Active", str(lang_active), f"out of 22"), unsafe_allow_html=True)
    with c4:
        st.markdown(stat_card("New Farmers", f"{new_farmers:,}", "joined this month"), unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # Charts row 1
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown('<div class="gs-section"><div class="gs-section-title">Query Type Breakdown</div>', unsafe_allow_html=True)
        tool_data = data.get("tool_usage", [])
        if tool_data:
            df = pd.DataFrame(tool_data)
            st.bar_chart(df.set_index("tool")["count"], height=200, use_container_width=True)
        else:
            st.markdown('<div style="text-align:center;color:#6B7280;padding:60px 0;font-size:13px">Mandi 42%&nbsp;&nbsp;Weather 28%&nbsp;&nbsp;Schemes 18%&nbsp;&nbsp;Crop 12%<br><br>No data yet</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_right:
        st.markdown('<div class="gs-section"><div class="gs-section-title">Language Distribution</div>', unsafe_allow_html=True)
        lang_data = data.get("language_distribution", [])
        if lang_data:
            df = pd.DataFrame(lang_data)
            st.bar_chart(df.set_index("language")["count"], height=200, use_container_width=True)
        else:
            st.markdown('<div style="text-align:center;color:#6B7280;padding:60px 0;font-size:13px">Hindi 38%&nbsp;&nbsp;Tamil 22%&nbsp;&nbsp;Telugu 18%&nbsp;&nbsp;Marathi 12%&nbsp;&nbsp;Others 10%<br><br>No data yet</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Charts row 2
    col_left2, col_right2 = st.columns(2)

    with col_left2:
        st.markdown('<div class="gs-section"><div class="gs-section-title">Calls by State — India Map</div>', unsafe_allow_html=True)
        st.markdown('<div style="background:#F3F4F6;border-radius:8px;height:180px;display:flex;align-items:center;justify-content:center;color:#9CA3AF;font-size:13px">[ Choropleth map — darker = more calls ]</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col_right2:
        st.markdown('<div class="gs-section"><div class="gs-section-title">Daily Call Volume — 30 Days</div>', unsafe_allow_html=True)
        daily = data.get("call_volume_30d", [])
        if daily:
            df = pd.DataFrame(daily)
            st.line_chart(df.set_index("date"), height=180, use_container_width=True)
        else:
            st.markdown('<div class="gs-empty" style="height:180px;display:flex;align-items:center;justify-content:center">No historical data yet</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Bottom lists
    top_states = data.get("top_states", [])

    col_l, col_r = st.columns(2)

    with col_l:
        tool_data = data.get("tool_usage", [])
        commodities = [t["tool"] for t in tool_data[:5]] if tool_data else ["Wheat", "Rice", "Tomato", "Onion", "Cotton"]
        items_html = "".join(
            f'<div style="padding:10px 0;border-bottom:1px solid #F3F4F6;font-size:13px;color:#374151">{i+1}.&nbsp;&nbsp;{c}</div>'
            for i, c in enumerate(commodities[:5])
        )
        st.markdown(f'<div class="gs-section"><div class="gs-section-title">Top Commodities Queried</div>{items_html}</div>', unsafe_allow_html=True)

    with col_r:
        if not top_states:
            top_states = ["Uttar Pradesh", "Maharashtra", "Andhra Pradesh", "Rajasthan", "Tamil Nadu"]
        items_html = "".join(
            f'<div style="padding:10px 0;border-bottom:1px solid #F3F4F6;font-size:13px;color:#374151">{i+1}.&nbsp;&nbsp;{s}</div>'
            for i, s in enumerate(top_states[:5])
        )
        st.markdown(f'<div class="gs-section"><div class="gs-section-title">Top States by Calls</div>{items_html}</div>', unsafe_allow_html=True)
