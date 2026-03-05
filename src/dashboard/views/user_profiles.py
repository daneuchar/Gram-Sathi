import streamlit as st
from dashboard.api import get
from dashboard.theme import GLOBAL_CSS, tag


def render():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    data = get("/api/dashboard/users", params={"page": 1, "per_page": 1})
    total = data.get("total", 0)

    st.markdown(f"""
    <div class="gs-topbar">
        <div class="gs-page-title">User Profiles</div>
        <div style="font-size:14px;color:#6B7280;font-weight:500">{total:,} total farmers</div>
    </div>
    """, unsafe_allow_html=True)

    # Filters
    f1, f2, f3, _ = st.columns([3, 2, 2, 5])
    search = f1.text_input("", placeholder="Search by phone or name...", label_visibility="collapsed")
    state_filter = f2.selectbox("State", ["State", "UP", "Tamil Nadu", "AP", "Maharashtra", "Rajasthan", "Karnataka", "West Bengal", "Telangana"], label_visibility="collapsed")
    crop_filter = f3.selectbox("Crop Type", ["Crop Type", "Wheat", "Rice", "Tomato", "Cotton", "Bajra", "Ragi", "Jute", "Chilli", "Maize", "Jowar", "Mustard"], label_visibility="collapsed")

    page = st.session_state.get("up_page", 1)
    params: dict = {"page": page, "per_page": 20}
    if search:
        params["phone"] = search
    if state_filter != "State":
        params["state"] = state_filter
    if crop_filter != "Crop Type":
        params["crop"] = crop_filter

    data = get("/api/dashboard/users", params=params)
    if "error" in data:
        st.error(f"Failed to load users: {data['error']}")
        return

    users = data.get("users", [])
    total = data.get("total", 0)

    # Table
    st.markdown('<div class="gs-section" style="padding:0">', unsafe_allow_html=True)
    rows = ""

    for user in users:
        phone = user.get("phone", "")
        name = user.get("name") or "<span style='color:#9CA3AF'>(Unknown)</span>"
        state = user.get("state", "—") or "—"
        crops = user.get("crops", "") or ""
        crop_tags = " ".join(tag(c.strip()) for c in crops.split(",") if c.strip()) if crops else "—"
        calls = user.get("call_count", 0) or 0
        rows += f"""
        <tr>
            <td>+91 {phone}</td>
            <td>{name}</td>
            <td>{state}</td>
            <td>{crop_tags}</td>
            <td>{calls}</td>
            <td style="color:#9CA3AF;text-align:right">›</td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="6" style="text-align:center;color:#9CA3AF;padding:40px">No farmers found</td></tr>'

    st.markdown(f"""
    <table class="gs-table">
        <thead>
            <tr>
                <th>Phone Number</th>
                <th>Name</th>
                <th>State</th>
                <th>Crops</th>
                <th>Total Calls</th>
                <th></th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # Profile detail panel (show first user if exists)
    if users:
        u = users[0]
        name = u.get("name") or "Unknown"
        phone = u.get("phone", "")
        state = u.get("state", "—") or "—"
        district = u.get("district", "—") or "—"
        lang = u.get("language", "—") or "—"
        land = u.get("land_acres", "—")
        crops = u.get("crops", "") or ""
        calls = u.get("call_count", 0) or 0
        created = u.get("created_at", "—") or "—"

        # Calculate profile completeness
        fields = [u.get("name"), u.get("state"), u.get("district"), u.get("language"), u.get("crops"), u.get("land_acres")]
        filled = sum(1 for f in fields if f)
        pct = round(filled / len(fields) * 100)

        st.markdown(f"""
        <div style="border-left:4px solid #2338E0;padding:16px 20px;background:#fff;border:1px solid #E5E7EB;border-radius:0 8px 8px 0;margin-top:12px;font-size:13px">
            <div style="font-size:12px;color:#6B7280;margin-bottom:8px">Profile Detail Drawer — slides in from right when you click ›</div>
            <div style="font-weight:700;font-size:15px;margin-bottom:8px">{name} / +91 {phone}</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 24px;color:#374151">
                <span>State: {state}</span><span>District: {district}</span>
                <span>Language: {lang}</span><span>Land Size: {land} acres</span>
                <span>Crops: {crops}</span><span>First Call: {created[:10] if isinstance(created, str) and len(created) >= 10 else created}</span>
                <span>Total Calls: {calls}</span><span></span>
            </div>
            <div style="margin-top:12px;font-size:12px;color:#6B7280">Profile Completeness</div>
            <div class="gs-progress-wrap"><div class="gs-progress-bar" style="width:{pct}%"></div></div>
            <div style="font-size:11px;color:#9CA3AF;margin-top:2px">{pct}%</div>
        </div>
        """, unsafe_allow_html=True)
