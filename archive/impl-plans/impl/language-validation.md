# Language Validation — Amazon Nova

> Fill this in during Task 06 after running actual Nova API calls.

## Amazon Nova Language Support Summary

| Language | Official Support | Guardrails Optimized | Verdict |
|----------|-----------------|---------------------|---------|
| Hindi (hi-IN) | ✅ Yes — GA | ✅ Yes | Production ready |
| Tamil (ta-IN) | ⚠️ Best-effort (200+ languages) | ❌ No | Validate in testing |
| Telugu (te-IN) | ⚠️ Best-effort | ❌ No | Validate in testing |
| Marathi (mr-IN) | ⚠️ Best-effort | ❌ No | Validate in testing |
| Bengali (bn-IN) | ⚠️ Best-effort | ❌ No | Validate in testing |

**Sources:**
- [AWS Nova Service Card](https://docs.aws.amazon.com/ai/responsible-ai/nova-micro-lite-pro/overview.html)
- [AWS re:Post](https://repost.aws/questions/QUT8IohzWxQzKPqCH5s2lCcA/what-languages-are-supported-in-amazon-nova)

---

## Hindi Test Results

| Test | Input | Nova Response | Language | Pass? |
|------|-------|--------------|----------|-------|
| Mandi price | "Jaipur mandi mein gehun ka bhav batao" | [TO FILL] | [TO FILL] | [TO FILL] |
| Weather | "Kal ka mausam kaisa rahega?" | [TO FILL] | [TO FILL] | [TO FILL] |
| Scheme | "PM Kisan yojana eligible hoon?" | [TO FILL] | [TO FILL] | [TO FILL] |

## Tamil Test Results

| Test | Input | Nova Response | Language | Acceptable? |
|------|-------|--------------|----------|-------------|
| Mandi price | "Jaipur mandi il tomato vilai enna?" | [TO FILL] | [TO FILL] | [TO FILL] |
| Scheme | "En nilam 2 acre. Enna scheme kidaikum?" | [TO FILL] | [TO FILL] | [TO FILL] |

## Mitigation Plan (if Tamil quality is low)

**Option A — Prompt engineering** (try first, zero cost):
```python
# Add to system prompt when language is Tamil:
"IMPORTANT: The farmer speaks Tamil (ta-IN). You MUST respond entirely in Tamil script. Never use English."
```

**Option B — Explicit language instruction per turn:**
```python
user_text = f"[Respond in Tamil only] {transcript}"
```

**Option C — Sarvam LLM fallback** (if Nova Tamil quality unacceptable):
- Use Sarvam's own LLM API for Tamil language turns
- Route by detected language: Hindi → Nova, Tamil → Sarvam LLM
