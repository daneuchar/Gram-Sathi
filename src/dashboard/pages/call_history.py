import streamlit as st
import pandas as pd
from dashboard.api import get


def render():
    st.header("Call History")

    col1, col2, col3 = st.columns(3)
    language = col1.text_input("Language filter", value="")
    state = col2.text_input("State filter", value="")
    page = col3.number_input("Page", min_value=1, value=1, step=1)

    params: dict = {"page": page, "per_page": 20}
    if language:
        params["language"] = language
    if state:
        params["state"] = state

    data = get("/api/dashboard/calls", params=params)
    if "error" in data:
        st.error(f"Failed to load calls: {data['error']}")
        return

    calls = data.get("calls", [])
    if calls:
        df = pd.DataFrame(calls)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No calls found.")
