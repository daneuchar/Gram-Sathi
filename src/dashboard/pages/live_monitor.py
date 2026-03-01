import time
import streamlit as st
from dashboard.api import get
from dashboard.config import POLL_INTERVAL_SECONDS


def render():
    st.header("Live Monitor")

    data = get("/api/dashboard/calls", params={"status": "in-progress", "per_page": 50})
    if "error" in data:
        st.error(f"Failed to load active calls: {data['error']}")
        return

    calls = data.get("calls", [])
    if not calls:
        st.info("No active calls right now.")
    else:
        for call in calls:
            with st.container(border=True):
                cols = st.columns(4)
                cols[0].write(f"**Phone:** {call.get('phone', '')}")
                cols[1].write(f"**Language:** {call.get('language_detected', 'N/A')}")
                cols[2].write(f"**Duration:** {call.get('duration_seconds', 0)}s")
                cols[3].write(f"**Status:** {call.get('status', '')}")

    time.sleep(POLL_INTERVAL_SECONDS)
    st.rerun()
