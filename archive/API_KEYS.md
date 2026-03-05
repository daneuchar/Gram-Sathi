# API Keys Setup Guide

How to obtain every credential required to run Gram Saathi locally.

---

## Quick Reference

| Key | Service | Free Tier | Time to get |
|-----|---------|-----------|-------------|
| `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` | Amazon Bedrock (Nova Lite) | Pay-per-use | ~10 min |
| `SARVAM_API_KEY` | Sarvam AI (ASR + TTS) | Free trial available | ~5 min |
| `EXOTEL_API_KEY` + `EXOTEL_API_TOKEN` + `EXOTEL_ACCOUNT_SID` + `EXOTEL_PHONE_NUMBER` | Exotel telephony | Paid, trial available | ~30 min |
| `INDIAN_API_KEY` | IndianAPI.in (weather) | Free tier | ~2 min |
| `DATA_GOV_API_KEY` | data.gov.in (mandi prices) | Free | ~5 min |
| `AMAZON_Q_APP_ID` | Amazon Q Business (schemes) | Optional for prototype | ~30 min |

---

## 1. AWS Credentials (Bedrock + Amazon Q)

Used for: **Amazon Nova Lite LLM** and optionally **Amazon Q Business** (government schemes).

### Step 1 — Create an IAM User

1. Log in to [AWS Console](https://console.aws.amazon.com)
2. Go to **IAM → Users → Create user**
3. Username: `gramvaani-dev`
4. Attach policies directly:
   - `AmazonBedrockFullAccess`
   - `QBusinessFullAccess` *(only if using Amazon Q)*
5. Click **Create user**

### Step 2 — Create Access Keys

1. Open the user → **Security credentials** tab
2. **Create access key** → use case: *Application running outside AWS*
3. Copy `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`

### Step 3 — Enable Nova Lite in Bedrock

1. Go to **Amazon Bedrock** → **Model access** (ap-south-1 region)
2. Click **Manage model access**
3. Enable **Amazon Nova Lite** (and Nova Pro if needed)
4. Wait ~2 minutes for activation

```env
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=ap-south-1
BEDROCK_MODEL_ID=amazon.nova-lite-v1:0
```

> **Cost estimate:** Nova Lite costs ~$0.00006/1K input tokens + $0.00024/1K output tokens. A typical 3-minute farmer call ≈ $0.002.

---

## 2. Sarvam AI (ASR + TTS)

Used for: **Speech-to-text** (Saaras v3, 22 Indian languages) and **Text-to-speech** (Bulbul v1).

### Steps

1. Go to [sarvam.ai](https://sarvam.ai) → **Get API Access** or [dashboard.sarvam.ai](https://dashboard.sarvam.ai)
2. Sign up with your email
3. Verify email → dashboard opens
4. Go to **API Keys** → **Generate Key**
5. Copy the key

```env
SARVAM_API_KEY=your-key-here
```

> **Free tier:** Sarvam offers a free trial with limited requests. Sufficient for prototyping.

---

## 3. Exotel (Telephony — Missed Call + Callback + Audio Stream)

Used for: **Receiving missed calls**, **triggering outbound callbacks**, and **streaming audio** to/from farmers.

### Steps

1. Go to [exotel.com](https://exotel.com) → **Start Free Trial**
2. Complete KYC (Indian phone number required)
3. Once approved, log in to the [Exotel Dashboard](https://my.exotel.com)

### Get your credentials

| Credential | Where to find |
|------------|--------------|
| `EXOTEL_ACCOUNT_SID` | Dashboard → top-right corner (e.g. `gramvaani1`) |
| `EXOTEL_API_KEY` | **Settings → API** → generate key |
| `EXOTEL_API_TOKEN` | Same page as API key |
| `EXOTEL_PHONE_NUMBER` | **Phone Numbers** → buy/assign a virtual number |

### Configure the virtual number

1. Go to **Phone Numbers** → select your ExoPhone
2. Set **App for Calls** → point to your webhook URL:
   - Missed call webhook: `https://your-domain/webhooks/missed-call`
   - Call status callback: `https://your-domain/webhooks/call-status`
3. For local dev, use [ngrok](https://ngrok.com) to expose your local server:
   ```bash
   ngrok http 8000
   # Use the https URL it gives you as your webhook base
   ```

```env
EXOTEL_API_KEY=your-api-key
EXOTEL_API_TOKEN=your-api-token
EXOTEL_ACCOUNT_SID=your-account-sid
EXOTEL_PHONE_NUMBER=+91XXXXXXXXXX
```

> **Note:** Exotel requires Indian business registration for production. The trial account works for testing with verified numbers.

---

## 4. IndianAPI.in (Weather Forecast)

Used for: **5-day hyperlocal weather forecast** per district.

### Steps

1. Go to [indianapi.in](https://indianapi.in)
2. Click **Get API Key** → Sign up (free)
3. Dashboard → **My API Keys** → copy the key

```env
INDIAN_API_KEY=your-key-here
```

> **Free tier:** 100 requests/day. Sufficient for prototyping (weather is cached 2 hours).

---

## 5. data.gov.in (Mandi Prices)

Used for: **Real-time agricultural commodity prices** from 1,266 mandis across India.

### Steps

1. Go to [data.gov.in](https://data.gov.in)
2. Click **Sign In / Register** (top right)
3. Register with email + Aadhaar or mobile OTP
4. After login, go to [data.gov.in/user/me/apps](https://data.gov.in/user/me/apps)
5. Click **Add App** → give it a name → **Get API Key**
6. Copy the API key

```env
DATA_GOV_API_KEY=your-key-here
```

> **Free:** No cost. The mandi prices dataset (`9ef84268-d588-465a-a308-a864a43d0070`) is publicly available.

---

## 6. Amazon Q Business (Government Schemes) — Optional

Used for: **Querying 1,000+ government schemes** (PM Kisan, PM Fasal Bima, etc.) for farmer eligibility.

> **Skip for initial prototype** — the code stubs gracefully when `AMAZON_Q_APP_ID` is empty.

### Steps (if you want full scheme support)

1. In AWS Console → go to **Amazon Q Business** (ap-south-1)
2. **Create application** → name: `gramvaani-schemes`
3. **Create index** → choose Enterprise index (or Starter for testing)
4. **Add data source** → upload the MyScheme.gov.in dataset:
   - Download from [HuggingFace: shrijayan/gov_myscheme](https://huggingface.co/datasets/shrijayan/gov_myscheme)
   - Upload as S3 data source or use the web crawler pointing to [myscheme.gov.in](https://myscheme.gov.in)
5. **Sync** the data source (takes ~10–30 min for 1,000+ schemes)
6. Copy the **Application ID** and **Index ID**

```env
AMAZON_Q_APP_ID=your-app-id
AMAZON_Q_INDEX_ID=your-index-id
```

> **Cost:** Amazon Q Business Lite starts at $3/user/month. Use a single user for the service account.

---

## Setting Up Your .env File

```bash
cp .env.example .env
# Fill in the values above
```

Your `.env` should look like:

```env
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
AWS_DEFAULT_REGION=ap-south-1
BEDROCK_MODEL_ID=amazon.nova-lite-v1:0

SARVAM_API_KEY=sk-sarvam-xxxxxxxx

EXOTEL_API_KEY=xxxxxxxx
EXOTEL_API_TOKEN=xxxxxxxx
EXOTEL_ACCOUNT_SID=youraccountsid
EXOTEL_PHONE_NUMBER=+911234567890

INDIAN_API_KEY=xxxxxxxx
DATA_GOV_API_KEY=xxxxxxxx

AMAZON_Q_APP_ID=          # leave blank to skip schemes
AMAZON_Q_INDEX_ID=        # leave blank to skip schemes

DATABASE_URL=postgresql+asyncpg://gramvaani:gramvaani@localhost:5432/gramvaani
DEBUG=false
```

---

## Running the App

```bash
# Start postgres
docker compose up postgres -d

# Start backend (in one terminal)
PYTHONPATH=src uv run uvicorn app.main:app --reload

# Start dashboard (in another terminal)
PYTHONPATH=src uv run streamlit run src/dashboard/app.py

# Run tests
PYTHONPATH=src uv run pytest src/tests/ -v
```

For local webhook testing (Exotel):
```bash
ngrok http 8000
# Update your Exotel virtual number webhooks to use the ngrok URL
```
