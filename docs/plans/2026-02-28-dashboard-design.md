# Gram Saathi — Streamlit Dashboard Wireframe Design

**Date:** 2026-02-28
**Author:** Design session (brainstormed)
**Status:** Approved

---

## Context

The Streamlit dashboard is used by NGO/Government operators monitoring Gram Saathi's impact. It runs on desktop and follows a professional/government visual tone — clean, neutral, blue/white.

## User

**Primary:** NGO/Government operator monitoring call volume, farmer engagement, query patterns, and system uptime.

## Design Decisions

- **Layout:** Sidebar navigation (multi-page), not tabs or single scroll
- **Sidebar:** Icon-only (64px) by default, expands to 240px with labels on hover/toggle
- **Active state:** Blue left border + filled icon
- **Background:** #F8F9FA (light grey content area), white sidebar
- **Tone:** Professional/government — clean, neutral, blue/white

---

## Pages

### 1. Overview (Home)

The landing page surfaces all 3 operator priorities at once.

**Top row — 3 KPI cards:**
- Active Calls (live green pulse)
- Calls Today (with % change vs yesterday)
- Total Farmers Served (with % change vs last week)

**Date range toggle:** Today / This Week

**Middle row — 2 charts:**
- Calls Over Time (7-day bar chart)
- Top Query Types (horizontal bar: Mandi 42%, Weather 28%, Schemes 18%, Crop 12%)

**Bottom — Alerts panel:**
- Red = critical (e.g. failed callbacks)
- Yellow = warning (e.g. high API latency)

---

### 2. Live Monitor

Real-time active call cards, WebSocket-updated.

**Each card shows:**
- Masked phone number (last 5 digits hidden)
- Language detected
- Live call duration counter
- State/region
- Scrollable transcript (auto-scrolls to latest)
- Bot "typing..." indicator while LLM responds

Cards appear/disappear as calls start/end.

---

### 3. Call History

Paginated table of all past calls.

**Columns:** Phone, Language, State, Duration, Topic icons (💰🌾☁️📋)

**Filters:** Search by phone, Language dropdown, State dropdown, Date range

**Click `>`** opens right-side drawer with:
- Full call metadata (date, district, tools used)
- Full scrollable transcript

Pagination: 20 per page.

---

### 4. User Profiles

Progressive farmer profiles built through conversation.

**Columns:** Phone, Name (or "Unknown"), State, Crops, Total Calls

**Filters:** Search by phone/name, State, Crop

**Click `>`** opens profile drawer with:
- Contact + location details
- Language, land size, crops
- First/last call dates, total call count
- Profile completeness progress bar (% of fields populated)
- Last 3 calls with topics

---

### 5. Analytics

Aggregated impact metrics with date range filter and CSV export.

**Top row — 3 KPI cards:**
- Total Calls (period)
- Average Call Duration
- Languages Active

**Charts:**
- Query Type Breakdown (horizontal bar)
- Language Distribution (horizontal bar)
- Calls by State (India choropleth map, darker = more calls)
- Daily Call Volume (30-day line chart)

**Bottom ranked lists:**
- Top Commodities Queried
- Top States by Calls

---

### 6. System Health

Service uptime and latency monitoring, auto-refreshes every 10 seconds.

**Service status table:**
- Each service: colored dot (green/yellow/red), status label, key metric
- Services: FastAPI, Sarvam ASR, Sarvam TTS, Amazon Bedrock, Amazon Q Business, Exotel, PostgreSQL, Redis, data.gov.in, IndianAPI.in

**Charts:**
- End-to-End Latency (1-hour line chart, with 1.5s target line)
- Error Rate table (24h): failed callbacks, ASR/LLM/TTS/tool errors

**Cache Hit Rate:**
- Mandi prices and Weather — progress bars

---

## Visual Spec

| Element | Value |
|---|---|
| Sidebar width (collapsed) | 64px |
| Sidebar width (expanded) | 240px |
| Content background | #F8F9FA |
| Sidebar background | #FFFFFF |
| Active nav accent | Blue left border |
| Primary accent color | Blue (#1E40AF or similar govt blue) |
| KPI card background | #FFFFFF with subtle shadow |
| Alert red | #DC2626 |
| Alert yellow | #D97706 |
| Success green | #16A34A |
| Font | System sans-serif (Streamlit default) |
