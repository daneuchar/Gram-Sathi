import streamlit as st
import pandas as pd
from dashboard.api import get


def render():
    st.header("Overview")

    data = get("/api/dashboard/stats")
    if "error" in data:
        st.error(f"Failed to load stats: {data['error']}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Calls", data.get("active_calls", 0))
    c2.metric("Calls Today", data.get("calls_today", 0))
    c3.metric("Farmers Served", data.get("total_farmers", 0))
    c4.metric("Avg Duration (s)", data.get("avg_duration_seconds", 0))

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Call Volume")
        st.info("Call volume chart will populate with historical data.")

    with col_right:
        st.subheader("Query Types")
        analytics = get("/api/dashboard/analytics")
        if "error" not in analytics:
            tool_data = analytics.get("tool_usage", [])
            if tool_data:
                df = pd.DataFrame(tool_data)
                st.bar_chart(df, x="tool", y="count")
            else:
                st.info("No tool usage data yet.")
        else:
            st.warning("Could not load analytics.")

    st.subheader("Alerts")
    if data.get("active_calls", 0) > 50:
        st.warning("High number of active calls!")
    else:
        st.success("All systems normal.")
