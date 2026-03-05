import streamlit as st
from dashboard.theme import GLOBAL_CSS

st.set_page_config(page_title="Gram Saathi", layout="wide", page_icon="🌾", initial_sidebar_state="expanded")

# Inject global CSS early so sidebar is styled
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

PAGES = [
    ("Overview", "overview"),
    ("Live Monitor", "live_monitor"),
    ("Call History", "call_history"),
    ("User Profiles", "user_profiles"),
    ("Analytics", "analytics"),
    ("System Health", "system_health"),
]

with st.sidebar:
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;padding:8px 0 20px 0">'
        '<div style="background:#2338E0;color:#fff;width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14px">G</div>'
        '<div style="font-size:17px;font-weight:700;color:#111827">Gram Saathi</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    selection = st.radio(
        "nav",
        [p[0] for p in PAGES],
        label_visibility="collapsed",
    )
    st.markdown(
        '<div style="position:absolute;bottom:16px;left:16px;font-size:11px;color:#9CA3AF">v1.0</div>',
        unsafe_allow_html=True,
    )

page_module = dict(PAGES)[selection]

if page_module == "overview":
    from dashboard.views.overview import render
elif page_module == "live_monitor":
    from dashboard.views.live_monitor import render
elif page_module == "call_history":
    from dashboard.views.call_history import render
elif page_module == "user_profiles":
    from dashboard.views.user_profiles import render
elif page_module == "analytics":
    from dashboard.views.analytics import render
else:
    from dashboard.views.system_health import render

render()
