# Gram Saathi — Prototype Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement each task file.

**Goal:** Build a working prototype of Gram Saathi — a zero-internet AI voice service for rural Indian farmers via missed calls.

**Architecture:** FastAPI backend + Pipecat voice pipeline + Sarvam ASR/TTS + Amazon Nova (Bedrock) LLM + PostgreSQL + Redis + Streamlit dashboard. Each feature track is an independent git branch, allowing parallel development via worktrees.

**Tech Stack:**
- Backend: Python 3.11, FastAPI, Pipecat
- LLM: Amazon Bedrock — Nova Pro (`amazon.nova-pro-v1:0`)
- ASR/TTS: Sarvam AI (Saaras v3 / Bulbul v3)
- Telephony: Exotel (missed call + callback + WebSocket audio)
- DB: PostgreSQL 15, Redis 7
- Dashboard: Streamlit 1.32
- Infra: Docker Compose

---

## Amazon Nova Language Support (Documented)

| Language | Support Level | Notes |
|----------|--------------|-------|
| **Hindi** | ✅ Officially supported | One of 9 GA languages, one of 15 optimized. Use confidently. |
| **Tamil** | ⚠️ Best-effort (200+ languages) | Not in official GA list. Safety guardrails not optimized. **Must validate completions in testing.** |
| Telugu, Kannada, Marathi, Bengali, etc. | ⚠️ Best-effort | Same caveat as Tamil. Sarvam ASR/TTS handles these — Nova only needs to understand transcript text. |

**Mitigation for Tamil/other languages:** Nova receives transcribed text (not raw audio) from Sarvam ASR. Output quality depends on Nova's text understanding. Add a validation test suite for each language in Task 06.

**Sources:**
- [AWS Nova Service Card](https://docs.aws.amazon.com/ai/responsible-ai/nova-micro-lite-pro/overview.html)
- [AWS re:Post — Nova language support](https://repost.aws/questions/QUT8IohzWxQzKPqCH5s2lCcA/what-languages-are-supported-in-amazon-nova)
- [Amazon Nova Models page](https://aws.amazon.com/nova/models/)

---

## Parallel Development Tracks

Each track is an **independent git branch + worktree**. They can be built simultaneously by separate agents.

| # | Task File | Branch | Description | Depends On |
|---|-----------|--------|-------------|------------|
| 01 | `01-backend-foundation.md` | `feat/backend-foundation` | FastAPI app, DB schema, Docker | — |
| 02 | `02-telephony-gateway.md` | `feat/telephony` | Exotel webhooks, missed call, callback | 01 |
| 03 | `03-voice-pipeline.md` | `feat/voice-pipeline` | Pipecat + Sarvam ASR + Nova + Sarvam TTS | 01 |
| 04 | `04-tools-apis.md` | `feat/tools` | Mandi, Weather, Schemes, Crop advisory tools | 01 |
| 05 | `05-dashboard.md` | `feat/dashboard` | Streamlit dashboard (all 6 pages) | 01 |
| 06 | `06-integration-testing.md` | `feat/integration` | E2E tests, language validation, load test | 02, 03, 04, 05 |

## Git Worktree Setup

```bash
# One-time: init git repo at project root
cd /Users/danieleuchar/workspace/gramvaani
git init
git add .
git commit -m "chore: initial project scaffold"

# Create worktree per track
git worktree add ../gramvaani-backend feat/backend-foundation
git worktree add ../gramvaani-telephony feat/telephony
git worktree add ../gramvaani-voice feat/voice-pipeline
git worktree add ../gramvaani-tools feat/tools
git worktree add ../gramvaani-dashboard feat/dashboard
```

## Agent Team Assignment

```
Team Lead (orchestrator)
├── Agent A → Task 01 (backend-foundation) — blocks all others
├── Agent B → Task 03 (voice-pipeline)     — start after 01
├── Agent C → Task 04 (tools-apis)         — start after 01
├── Agent D → Task 05 (dashboard)          — start after 01
└── Agent E → Task 06 (integration)        — start after 02-05 done
     (Task 02/telephony runs inline with Agent B after voice pipeline)
```

## Environment Variables Required

```bash
# Bedrock
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=ap-south-1
BEDROCK_MODEL_ID=amazon.nova-pro-v1:0

# Sarvam
SARVAM_API_KEY=

# Exotel
EXOTEL_API_KEY=
EXOTEL_API_TOKEN=
EXOTEL_ACCOUNT_SID=
EXOTEL_PHONE_NUMBER=

# External APIs
DATA_GOV_API_KEY=
INDIAN_API_KEY=

# Amazon Q Business
AMAZON_Q_APP_ID=
AMAZON_Q_INDEX_ID=

# Database
DATABASE_URL=postgresql://gramvaani:gramvaani@localhost:5432/gramvaani
REDIS_URL=redis://localhost:6379
```
