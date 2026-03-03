# Farmer Onboarding Design

**Date:** 2026-03-03

**Goal:** When a new phone number connects via the web UI, collect name, state, and district/village through a natural voice conversation, auto-detect language, save the profile to the database, and switch to the normal agricultural assistant mode.

---

## Web UI: Phone number input

The FastRTC `Stream` supports `additional_inputs` (extra Gradio components passed to every turn). A `gr.Textbox` for phone number is added in `main.py`. The handler receives it on the first audio turn and uses it to look up the profile. The record button stays disabled until the phone field is non-empty.

## Handler: new vs returning detection

On first turn, the handler queries the DB for the phone number:
- **Returning** (`user.name` is set) → load profile into `farmer_profile`, proceed to normal assistant mode immediately
- **New** (`user.name` is None, or user doesn't exist) → set `is_onboarding = True`, use onboarding system prompt

Handler tracks two new fields: `phone` and `is_onboarding`. Profile stored in `self.farmer_profile` and reused across all turns in the session.

## Onboarding conversation (Nova-driven)

Nova gets a different system prompt when `is_onboarding = True`:

> "You are GramSaathi, a voice assistant for Indian farmers. This farmer is calling for the first time. Detect their language from their speech and respond in the same language. Welcome them warmly, ask for their name, then ask for their state and district or village. Once you have all three, output `<<<PROFILE:{"name":"...","state":"...","district":"..."}>>>` on its own line, then immediately greet them by name and offer to help with farming questions."

Handler scans each Nova response for the `<<<PROFILE:...>>>` marker. When found:
1. Parse JSON, save name/state/district + detected language to DB
2. Strip the marker from the spoken response (farmer never hears it)
3. Set `is_onboarding = False`, load full profile into `self.farmer_profile`
4. All subsequent turns use the normal system prompt with profile context

Language is captured automatically — ASR detects it on the first utterance and the detected language code gets saved to the user record alongside name/state/district.

## Profile injected into normal turns

Once onboarded, `farmer_profile` (name, state, district, language) is passed to `process_turn_streaming` on every turn instead of `None`. Nova's normal system prompt gets a profile preamble:

> "Farmer profile — Name: {name}, State: {state}, District: {district}. Use this context when answering. Default weather and mandi queries to the farmer's state/district unless they specify otherwise."

## Files touched

| File | Change |
|---|---|
| `src/app/main.py` | Add `gr.Textbox` phone input to FastRTC Stream |
| `src/app/handlers/gram_saathi.py` | Accept phone, query DB, track `is_onboarding`, extract PROFILE marker |
| `src/app/pipeline/nova_client.py` | Accept `system_prompt` override parameter |
| `src/app/pipeline/pipeline.py` | Pass `farmer_profile` to Nova context, pass `system_prompt` |
| `src/app/database.py` (or new helper) | `get_or_create_user()`, `update_user_profile()` async functions |
