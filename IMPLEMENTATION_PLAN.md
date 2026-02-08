# Gram Vani - Implementation Plan
## Zero-Internet Rural AI using Amazon Bedrock

---

## Executive Summary

This document outlines the technical implementation plan for **Gram Vani** — an AI-powered voice service that enables 300M+ rural Indians to access crop advice, scheme eligibility, market prices, and weather alerts through **missed calls and voice callbacks**, without requiring internet or smartphones.

**Core AWS AI Services:**
- **Amazon Bedrock** — LLM processing for scheme matching, complex query handling, and conversational responses
- **Bedrock Knowledge Bases** — RAG over 400+ government schemes for eligibility matching (no Amazon Q required)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           GRAM VANI - SYSTEM ARCHITECTURE                        │
└─────────────────────────────────────────────────────────────────────────────────┘

     [Farmer]                    [Telephony Layer]              [Backend Services]
        │                               │                              │
        │  1. Missed Call               │                              │
        │ ─────────────────────────────>│  Exotel/Twilio               │
        │                               │     (India)                  │
        │                               │         │                    │
        │  2. Voice Callback            │         │ 3. Webhook         │
        │ <─────────────────────────────│         │ ─────────────────>│  Node.js API
        │                               │         │                    │      │
        │  4. Voice Interaction         │         │                    │      │
        │ <────────────────────────────>│         │                    │      ▼
        │     (Bhashini ASR/TTS)        │         │              ┌─────┴─────┐
        │                               │         │              │  Routing  │
        │                               │         │              │  Engine   │
        │                               │         │              └─────┬─────┘
        │                               │         │                    │
        │                               │         │         ┌───────────┼───────────┐
        │                               │         │         │           │           │
        │                               │         │         ▼           ▼           ▼
        │                               │         │   Decision Tree   Bedrock KB  Amazon Bedrock
        │                               │         │   (Simple FAQs)   (Scheme     (Complex Q&A,
        │                               │         │                  RAG)        Reasoning)
        │                               │         │         │           │           │
        │                               │         │         └───────────┼───────────┘
        │                               │         │                    │
        │                               │         │                    ▼
        │                               │         │              ┌─────────────┐
        │                               │         │              │  Gov APIs   │
        │                               │         │              │ PM-KISAN   │
        │                               │         │              │ eNAM, IMD  │
        │                               │         │              └─────────────┘
        │                               │         │                    │
        │                               │         │                    ▼
        │                               │         │              ┌─────────────┐
        │                               │         └──────────────>│ PostgreSQL  │
        │                               │                        │ (Profiles)  │
        │                               │                        └─────────────┘
```

---

## Phase 1: Foundation & Infrastructure

### 1.1 AWS Account Setup & IAM

| Task | Details |
|------|---------|
| Enable Bedrock | Enable Amazon Bedrock in AWS Console → Bedrock → Get started (enable model access: Claude, Titan) |
| Knowledge Bases | Bedrock → Knowledge bases → Create knowledge base (uses Bedrock embeddings + retrieval) |
| IAM Roles | Create roles with least-privilege for Bedrock (`bedrock:InvokeModel`, `bedrock:Retrieve`, `bedrock:InvokeModelWithResponseStream`), Lambda, API Gateway |
| VPC (optional) | If using VPC endpoints for Bedrock for data residency, configure private subnets |

### 1.2 Data Layer (PostgreSQL)

**Schema Design:**

```sql
-- Users/Farmers (built from call interactions)
CREATE TABLE farmers (
  id UUID PRIMARY KEY,
  phone_number VARCHAR(15) UNIQUE NOT NULL,
  language_preference VARCHAR(10) DEFAULT 'hi',
  state VARCHAR(50),
  district VARCHAR(100),
  crops TEXT[],  -- Array of crops they grow
  landholding_acres DECIMAL,
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

-- Interaction history (for personalization & context)
CREATE TABLE interactions (
  id UUID PRIMARY KEY,
  farmer_id UUID REFERENCES farmers(id),
  intent VARCHAR(50),  -- weather, prices, schemes, crop_advice
  query_text TEXT,
  response_summary TEXT,
  created_at TIMESTAMP
);

-- Proactive alert schedule
CREATE TABLE alert_schedule (
  id UUID PRIMARY KEY,
  farmer_id UUID REFERENCES farmers(id),
  alert_type VARCHAR(50),  -- weather, price_spike, scheme_deadline
  scheduled_for TIMESTAMP,
  status VARCHAR(20),  -- pending, sent, failed
  created_at TIMESTAMP
);
```

---

## Phase 2: Government Scheme Knowledge Base (Bedrock Knowledge Bases)

### 2.1 Why Bedrock Knowledge Bases for Scheme Matching?

- **RAG at scale:** Index 400+ government schemes (PDFs) in S3 — Bedrock handles embeddings and retrieval
- **Natural language queries:** "Mujhe PM-KISAN ke liye kaun se documents chahiye?" — Knowledge Base retrieves relevant scheme docs
- **Cite sources:** RetrieveAndGenerate returns citations — critical for scheme eligibility verification
- **Simplicity:** Single Bedrock stack — no separate Amazon Q subscription; pay-per-use only

### 2.2 Bedrock Knowledge Base Implementation Steps

| Step | Action | Details |
|------|--------|---------|
| 1 | Create Knowledge Base | Bedrock → Knowledge bases → Create knowledge base |
| 2 | Add Data Source | S3 bucket containing scheme PDFs; structure: `schemes/{category}/{scheme_name}.pdf` |
| 3 | Choose Embedding Model | Amazon Titan Embeddings G1 - Text (multilingual support) |
| 4 | Sync | Run ingestion job; Bedrock chunks and indexes documents |
| 5 | Configure Retrieval | Set `numberOfResults` (e.g., 5–10) for top-k retrieval |

### 2.3 Scheme Data Sources

| Source | Content | Format |
|--------|---------|--------|
| PM-KISAN | Farmer income support | API + PDF |
| State Agri Schemes | State-specific schemes | PDFs from state portals |
| eNAM | Mandi-linked schemes | API |
| NIC/India.gov.in | Central scheme repository | Download PDFs → upload to S3 |

### 2.4 Bedrock Knowledge Base Integration (RetrieveAndGenerate)

```javascript
// Node.js - Bedrock RetrieveAndGenerate (RAG in one call)
const { BedrockAgentRuntimeClient, RetrieveAndGenerateCommand } = require("@aws-sdk/client-bedrock-agent-runtime");

async function querySchemeEligibility(farmerContext, query) {
  const client = new BedrockAgentRuntimeClient({ region: "ap-south-1" });
  const prompt = `Farmer context: ${JSON.stringify(farmerContext)}. Query: ${query}`;
  
  const response = await client.send(new RetrieveAndGenerateCommand({
    input: { text: prompt },
    retrieveAndGenerateConfiguration: {
      type: "KNOWLEDGE_BASE",
      knowledgeBaseConfiguration: {
        knowledgeBaseId: process.env.KNOWLEDGE_BASE_ID,
        modelArn: "anthropic.claude-3-sonnet-20240229-v1:0",
        retrievalConfiguration: {
          vectorSearchConfiguration: {
            numberOfResults: 8,
          },
        },
      },
    },
  }));
  
  return {
    answer: response.output.text,
    citations: response.citations,
  };
}
```

---

## Phase 3: LLM Processing (Amazon Bedrock)

### 3.1 Bedrock Model Selection

| Use Case | Recommended Model | Rationale |
|----------|-------------------|------------|
| Complex Q&A, reasoning | **Claude 3 Sonnet** | Strong multilingual, good reasoning |
| Scheme matching synthesis | **Claude 3 Haiku** | Fast, cost-effective for structured output |
| Crop advice generation | **Claude 3 Sonnet** | Needs agricultural domain reasoning |
| Fallback / simple tasks | **Amazon Titan Text** | Lower cost for trivial tasks |

### 3.2 Bedrock Use Cases in Gram Vani

#### A. Scheme Eligibility (via RetrieveAndGenerate)

**Flow:** Knowledge Base retrieves relevant scheme snippets → Bedrock synthesizes a personalized eligibility summary in the farmer's language. Use `RetrieveAndGenerateCommand` for end-to-end RAG (retrieve + generate in one call).

```javascript
// RetrieveAndGenerate returns answer + citations directly
// For custom synthesis, use RetrieveCommand + InvokeModel separately:
const eligibilityPrompt = `
You are Gram Vani, a helpful AI for rural Indian farmers. 
Given the following scheme information from our knowledge base, 
create a SHORT (max 2-3 sentences) eligibility summary in ${language} 
for a farmer with: ${farmerContext}.
Keep it simple and actionable. Mention next steps if any.

Scheme info:
${retrievedContent}
`;
```

#### B. Complex Query Handling (LLM Fallback)

When decision trees or Knowledge Base retrieval cannot handle a query (e.g., "Mere bhai ke liye koi scheme hai jo unhe startup Shuru karne mein help kare?"), route to Bedrock:

```javascript
// Bedrock: Open-ended complex query
const complexQueryPrompt = `
Context: Farmer asking on behalf of family member. 
Query: ${userQuery}
Available capabilities: Schemes (PM-KISAN, state schemes), 
market prices (eNAM), weather (IMD), crop advice.

If query is about schemes, suggest they ask about specific scheme names.
If about weather/prices, provide generic guidance and ask them to 
specify crop/location for precise info.
Respond in ${language}, max 3 sentences, conversational tone.
`;
```

#### C. Crop Advice Generation

Combine IMD weather data + eNAM prices + Bedrock for advisory:

```javascript
const cropAdvicePrompt = `
Weather: ${weatherData}
Mandi prices (last 7 days): ${priceData}
Farmer's crops: ${crops}
District: ${district}

Provide 2-3 sentence crop advice in ${language}. 
Focus on: sowing timing, pest alert if applicable, 
harvest/market timing suggestion.
`;
```

### 3.3 Bedrock Invocation (Node.js)

```javascript
const { BedrockRuntimeClient, InvokeModelCommand } = require("@aws-sdk/client-bedrock-runtime");

async function invokeBedrock(prompt, modelId = "anthropic.claude-3-sonnet-20240229-v1:0") {
  const client = new BedrockRuntimeClient({ region: "ap-south-1" });
  const response = await client.send(new InvokeModelCommand({
    modelId,
    contentType: "application/json",
    accept: "application/json",
    body: JSON.stringify({
      anthropic_version: "bedrock-2023-05-31",
      max_tokens: 512,
      messages: [{ role: "user", content: prompt }],
      temperature: 0.3,
    }),
  }));
  const result = JSON.parse(new TextDecoder().decode(response.body));
  return result.content[0].text;
}
```

---

## Phase 4: Query Routing Engine

### 4.1 Routing Logic

```
User Query (from Bhashini ASR)
        │
        ▼
┌───────────────────┐
│ Intent Classifier │  ← Use Bedrock or a lightweight model
│ (weather/prices/  │     for fast intent detection
│  schemes/crop)    │
└─────────┬─────────┘
          │
    ┌─────┴─────┬─────────────┬─────────────┐
    ▼           ▼             ▼             ▼
 Decision   Gov API      Bedrock KB    Bedrock
   Tree     Direct      (Scheme       (Complex
 (Simple)   (Weather,   RAG)          Q&A)
            Prices)
```

### 4.2 Decision Tree (Simple Queries)

| Intent | Trigger Keywords (Hindi/English) | Handler |
|--------|----------------------------------|---------|
| Weather | मौसम, बारिश, weather | IMD API → Bedrock (format for voice) |
| Mandi prices | मंडी, भाव, दाम, price | eNAM API → Bedrock (format) |
| PM-KISAN status | PM-KISAN, पीएम किसान | PM-KISAN API (if Aadhaar linked) or Knowledge Base |
| Scheme list | योजना, scheme | Bedrock Knowledge Base |

### 4.3 Intent Classification (Bedrock)

Use a fast, low-token prompt for intent classification:

```javascript
const intentPrompt = `Classify intent into ONE of: weather, mandi_prices, scheme_eligibility, crop_advice, other. 
Query: "${userQuery}" 
Reply with ONLY the intent word.`;
```

---

## Phase 5: Voice Pipeline (Bhashini + Telephony)

### 5.1 Voice Flow

1. **Missed Call** → Exotel/Twilio detects → Webhook to Node.js
2. **Callback** → Initiate outbound call to farmer
3. **IVR Greeting** → "Namaste, Gram Vani hai. Aap kya janana chahte hain? Mauasam, mandi ke bhav, ya koi yojana?"
4. **User Speaks** → Audio stream to Bhashini ASR → Text
5. **Process** → Routing engine → Bedrock (Knowledge Base for schemes) → Response text
6. **TTS** → Bhashini TTS → Audio → Play to user
7. **Loop** until user hangs up or says "dhanyavad"

### 5.2 Bhashini Integration

- **ASR:** Bhashini ULCA API — supports 10+ Indian languages, handle noisy environments with `noise_reduction` params
- **TTS:** Bhashini TTS for natural Hindi/regional language output
- **Alternative:** Amazon Transcribe (supports Hindi, etc.) + Amazon Polly (Hindi voices) if Bhashini has latency issues

### 5.3 Exotel/Twilio Webhook

```javascript
// POST /webhook/missed-call
app.post("/webhook/missed-call", async (req, res) => {
  const { From } = req.body;  // Farmer's number
  await db.upsertFarmer(From);
  await telephonyService.initiateCallback(From);
  res.status(200).send();
});

// Webhook for answering machine / call connect
// Use Twilio <Stream> or Exotel's equivalent for bidirectional audio
```

---

## Phase 6: Proactive Alerts

### 6.1 Alert Types

| Alert Type | Trigger | Data Source | Action |
|------------|---------|-------------|--------|
| Weather warning | IMD forecast (heavy rain, hail, heat) | IMD API | Schedule outbound call to farmers in affected districts |
| Price spike | eNAM price change > X% | eNAM API | Alert farmers growing that crop |
| Scheme deadline | PM-KISAN installment, state scheme last date | DB + cron | Call farmers who haven't enrolled |

### 6.2 Implementation

- **Cron/Lambda:** Run every 6 hours (or event-driven via EventBridge)
- **Lambda:** Fetch IMD/eNAM data → Query farmers by district/crop → Insert into `alert_schedule`
- **Outbound Worker:** Node.js worker or Lambda polls `alert_schedule` → Exotel/Twilio outbound API → Pre-recorded or TTS message

---

## Phase 7: Government API Integrations

### 7.1 APIs to Integrate

| API | Purpose | Auth | Endpoint (example) |
|-----|---------|------|--------------------|
| PM-KISAN | Scheme status, beneficiary check | API key (Gov) | https://pmkisan.gov.in/... |
| eNAM | Mandi prices | Public / API key | https://enam.gov.in/... |
| IMD | Weather forecast | API key | https://mausam.imd.gov.in/... |

*Note: Actual endpoints and auth mechanism depend on government API documentation. Some may require registration.*

### 7.2 Data Sync for Bedrock Knowledge Base

- Periodically fetch scheme updates from gov portals → Store in S3 → Re-sync Knowledge Base
- Bedrock Knowledge Base supports incremental sync; use EventBridge + Lambda for weekly ingestion

---

## Phase 8: Security, Cost & Scaling

### 8.1 Security

- **PII:** Farmer phone numbers — encrypt at rest (PostgreSQL encryption), restrict access
- **Bedrock:** Use VPC endpoints if required for compliance
- **Secrets:** AWS Secrets Manager for API keys (Exotel, Bhashini, Gov APIs)
- **Rate limiting:** Per-phone rate limit to prevent abuse

### 8.2 Cost Optimization

| Service | Optimization |
|---------|---------------|
| Bedrock | Use Haiku for simple tasks; cache frequent responses (Redis) |
| Knowledge Base | Index only relevant scheme docs; tune `numberOfResults` to limit retrieval cost |
| Telephony | Bulk pricing with Exotel/Twilio; optimize call duration |
| Lambda | Right-size memory; use ARM (Graviton) for lower cost |

### 8.3 Scaling

- **Node.js API:** Deploy on ECS Fargate or Lambda + API Gateway
- **Database:** RDS PostgreSQL with read replicas for alert scheduling
- **Concurrent calls:** Exotel/Twilio scale horizontally; ensure backend can handle webhook burst

---

## Implementation Timeline

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| Phase 1: Foundation | 1 week | AWS setup, PostgreSQL schema, basic Node.js API |
| Phase 2: Knowledge Base | 1 week | S3 + Bedrock Knowledge Base, scheme ingestion, RetrieveAndGenerate |
| Phase 3: Bedrock | 1 week | Bedrock integration, prompts for all use cases |
| Phase 4: Routing | 3–4 days | Intent classifier, decision tree, routing logic |
| Phase 5: Voice | 1–2 weeks | Exotel/Twilio + Bhashini, end-to-end voice flow |
| Phase 6: Alerts | 1 week | Cron jobs, outbound calling |
| Phase 7: Gov APIs | 1 week | PM-KISAN, eNAM, IMD integration |
| Phase 8: Hardening | 1 week | Security, cost optimization, load testing |

**Total:** ~8–10 weeks for MVP

---

## Demo Checklist (3-Minute Hackathon Demo)

1. **Setup:** Nokia feature phone, speakerphone, backend dashboard on screen
2. **Call:** Give missed call from feature phone → Receive callback
3. **Query 1:** "Aaj mausam kaisa rahega?" → Weather response
4. **Query 2:** "Tomato ka bhav kya hai?" → Mandi price
5. **Query 3:** "Mujhe PM-KISAN ke liye eligibility batayein" → Bedrock Knowledge Base + Claude response
6. **Backend:** Show farmer profile built, alert schedule
7. **Impact:** "1% of UP feature phone users = 2M farmers"

---

## Summary: Bedrock + Knowledge Bases

| Component | Role |
|-----------|------|
| **Bedrock Knowledge Base** | RAG over 400+ schemes — retrieve relevant docs, return citations |
| **Bedrock (Claude)** | Generate responses, synthesize retrieval, crop advice, complex Q&A, intent classification |

**Flow:** retrieve (`RetrieveAndGenerate`) → synthesize (Claude) → Bhashini speaks. A single Bedrock stack delivers accurate, personalized, voice-friendly responses for rural farmers — no Amazon Q subscription required.

---

*Document version: 1.1 | Last updated: Feb 8, 2026 | Updated: Replaced Amazon Q with Bedrock Knowledge Bases*
