import streamlit as st
import pandas as pd
from dashboard.api import get


def render():
    st.header("Analytics")

    data = get("/api/dashboard/analytics")
    if "error" in data:
        st.error(f"Failed to load analytics: {data['error']}")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Language Distribution")
        lang_data = data.get("language_distribution", [])
        if lang_data:
            df = pd.DataFrame(lang_data)
            st.bar_chart(df, x="language", y="count")
        else:
            st.info("No language data yet.")

    with col2:
        st.subheader("Tool Usage")
        tool_data = data.get("tool_usage", [])
        if tool_data:
            df = pd.DataFrame(tool_data)
            st.bar_chart(df, x="tool", y="count")
        else:
            st.info("No tool usage data yet.")
