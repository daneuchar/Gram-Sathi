import streamlit as st
import pandas as pd
from dashboard.api import get


def render():
    st.header("User Profiles")

    page = st.number_input("Page", min_value=1, value=1, step=1)

    data = get("/api/dashboard/users", params={"page": page, "per_page": 20})
    if "error" in data:
        st.error(f"Failed to load users: {data['error']}")
        return

    users = data.get("users", [])
    if users:
        df = pd.DataFrame(users)
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No users found.")
