import streamlit as st
from dashboard.api import get
from dashboard.theme import GLOBAL_CSS, tag


def _fmt_duration(secs):
    if not secs:
        return "—"
    s = int(secs)
    return f"{s // 60}m {s % 60:02d}s"


def render():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    st.markdown('<div class="gs-page-title">Call History</div>', unsafe_allow_html=True)

    # Filters
    f1, f2, f3, f4, btn_col = st.columns([3, 2, 2, 2, 2])
    search = f1.text_input("", placeholder="Search by phone number...", label_visibility="collapsed")
    language = f2.selectbox("Language", ["Language", "Hindi", "Tamil", "Telugu", "Marathi", "Kannada", "Bengali"], label_visibility="collapsed")
    state = f3.selectbox("State", ["State", "UP", "Tamil Nadu", "AP", "Maharashtra", "Rajasthan", "Karnataka", "West Bengal", "Telangana"], label_visibility="collapsed")
    date_range = f4.selectbox("Date Range", ["Date Range", "Today", "This Week", "This Month", "All Time"], label_visibility="collapsed")

    page = st.session_state.get("ch_page", 1)

    with btn_col:
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        if st.button("Apply Filters", type="primary", use_container_width=True):
            st.session_state["ch_page"] = 1
            page = 1

    params: dict = {"page": page, "per_page": 20}
    if language not in ("Language", ""):
        params["language"] = language
    if state not in ("State", ""):
        params["state"] = state
    if search:
        params["phone"] = search

    data = get("/api/dashboard/calls", params=params)
    if "error" in data:
        st.error(f"Failed to load calls: {data['error']}")
        return

    calls = data.get("calls", [])
    total = data.get("total", 0)

    # Table
    st.markdown('<div class="gs-section" style="padding:0">', unsafe_allow_html=True)

    rows = ""
    for call in calls:
        phone = call.get("phone", "")
        lang = call.get("language_detected", "—")
        st_val = call.get("state", "—") or "—"
        dur = _fmt_duration(call.get("duration_seconds"))
        tools = call.get("tools_used", "") or ""
        topics = " ".join(tag(t.strip().title()) for t in tools.split(",") if t.strip()) if tools else "—"
        rows += f"""
        <tr>
            <td>+91 {phone}</td>
            <td>{lang}</td>
            <td>{st_val}</td>
            <td>{dur}</td>
            <td>{topics}</td>
            <td style="color:#9CA3AF;text-align:right">›</td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="6" style="text-align:center;color:#9CA3AF;padding:40px">No calls found</td></tr>'

    st.markdown(f"""
    <table class="gs-table">
        <thead>
            <tr>
                <th>Phone Number</th>
                <th>Language</th>
                <th>State</th>
                <th>Duration</th>
                <th>Topics</th>
                <th></th>
            </tr>
        </thead>
        <tbody>{rows}</tbody>
    </table>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # Pagination
    total_pages = max(1, (total + 19) // 20)
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    p_cols = st.columns([2, 1, 1, 1, 1, 6])
    if p_cols[0].button("‹ Prev", disabled=page <= 1):
        st.session_state["ch_page"] = page - 1
        st.rerun()
    p_cols[1].markdown(f"<div style='text-align:center;padding:8px;font-weight:700;color:#2338E0'>{page}</div>", unsafe_allow_html=True)
    if page + 1 <= total_pages and p_cols[2].button(str(page + 1)):
        st.session_state["ch_page"] = page + 1
        st.rerun()
    if total_pages > page + 1:
        p_cols[3].markdown("<div style='text-align:center;padding:8px;color:#9CA3AF'>...</div>", unsafe_allow_html=True)
    if p_cols[4].button("Next ›", disabled=page >= total_pages):
        st.session_state["ch_page"] = page + 1
        st.rerun()
    p_cols[5].markdown(f"<div style='text-align:right;padding:8px;font-size:12px;color:#9CA3AF'>Showing {(page-1)*20+1}–{min(page*20,total)} of {total} calls</div>", unsafe_allow_html=True)

    # Hint
    st.markdown("""
    <div style="border-left:4px solid #2338E0;padding:12px 16px;background:#EEF0FD;border-radius:0 6px 6px 0;margin-top:12px;font-size:12px;color:#374151">
        Click <b>›</b> on any row to open the Call Detail Drawer<br>
        <span style="color:#6B7280">Shows: full transcript, tools used, call metadata, district</span>
    </div>
    """, unsafe_allow_html=True)
