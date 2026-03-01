import streamlit as st

st.set_page_config(page_title="Gram Saathi Dashboard", layout="wide")

PAGES = {
    "Overview": "overview",
    "Live Monitor": "live_monitor",
    "Call History": "call_history",
    "User Profiles": "user_profiles",
    "Analytics": "analytics",
    "System Health": "system_health",
}

ICONS = {
    "Overview": "\U0001f4ca",
    "Live Monitor": "\U0001f534",
    "Call History": "\U0001f4cb",
    "User Profiles": "\U0001f464",
    "Analytics": "\U0001f4c8",
    "System Health": "\u2699\ufe0f",
}

with st.sidebar:
    st.title("Gram Saathi")
    selection = st.radio(
        "Navigation",
        list(PAGES.keys()),
        format_func=lambda x: f"{ICONS[x]} {x}",
    )

if selection == "Overview":
    from dashboard.pages.overview import render
elif selection == "Live Monitor":
    from dashboard.pages.live_monitor import render
elif selection == "Call History":
    from dashboard.pages.call_history import render
elif selection == "User Profiles":
    from dashboard.pages.user_profiles import render
elif selection == "Analytics":
    from dashboard.pages.analytics import render
else:
    from dashboard.pages.system_health import render

render()
