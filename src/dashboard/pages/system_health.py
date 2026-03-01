import streamlit as st
from dashboard.api import get


def render():
    st.header("System Health")

    if st.button("Refresh"):
        st.rerun()

    data = get("/api/health")
    if "error" in data:
        st.error(f"API is unreachable: {data['error']}")
    elif data.get("status") == "ok":
        st.success("API is healthy")
    else:
        st.warning(f"Unexpected response: {data}")
