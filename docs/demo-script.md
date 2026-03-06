# Gram Saathi — Live Demo Script

Two back-to-back calls that show the full farmer journey: onboarding → asking questions → calling back for more.

**Test page:** `https://gramsaathi.in/test` → click **Start Call**

---

## Call 1: First-Time Farmer (Onboarding + Quick Questions)

> Goal: Show how a new farmer registers by just talking, then immediately gets live market prices.

### Step 1 — Language Selection
| Speaker | Says |
|---------|------|
| Agent | "Welcome to Gram Saathi! What language do you prefer?" |
| You | **"Hindi"** |

### Step 2 — Name
| Speaker | Says |
|---------|------|
| Agent | "आपका नाम क्या है?" |
| You | **"Ramesh"** |

### Step 3 — State
| Speaker | Says |
|---------|------|
| Agent | "रमेश जी, आप किस राज्य से हैं?" |
| You | **"Haryana"** |

### Step 4 — District
| Speaker | Says |
|---------|------|
| Agent | "कौन से ज़िले से हैं?" |
| You | **"Karnal"** |

### Step 5 — Crops
| Speaker | Says |
|---------|------|
| Agent | "कौन सी फसलें उगाते हैं?" |
| You | **"Gehun aur dhan"** (wheat and rice) |

### Step 6 — Land Size
| Speaker | Says |
|---------|------|
| Agent | "कितने एकड़ ज़मीन है?" |
| You | **"Paanch ekad"** (5 acres) |

### Step 7 — Profile Saved, Agent Ready
| Speaker | Says |
|---------|------|
| Agent | "रमेश जी, नमस्ते! बताइए, क्या मदद करूँ?" |

> **Talking point:** "The farmer just registered by having a natural conversation — no forms, no app, no literacy required. All profile data is saved to our database."

### Step 8 — Mandi Price Query
| Speaker | Says |
|---------|------|
| You | **"Gehun ka bhav kya chal raha hai?"** (What's the wheat price?) |
| Agent | Fetches live price from data.gov.in and responds with price per quintal |

> **Talking point:** "That was a live API call to the Indian government's mandi data portal. The price you just heard is today's actual market rate."

### Step 9 — End Call
| Speaker | Says |
|---------|------|
| You | **"Dhanyavaad"** (Thank you) |
| Agent | Warm farewell, call disconnects automatically |

---

## Call 2: Returning Farmer (Schemes + Weather)

> Goal: Show the agent remembers the farmer and answers deeper questions about government schemes and weather.

**Click Start Call again.** The agent recognizes Ramesh from the phone number.

### Step 1 — Agent Greets by Name
| Speaker | Says |
|---------|------|
| Agent | "रमेश जी, नमस्ते! कैसे मदद करूँ?" |

> **Talking point:** "Notice the agent skipped onboarding — it remembered Ramesh from the first call. Name, location, crops, and land size are all on file."

### Step 2 — Government Scheme Query
| Speaker | Says |
|---------|------|
| You | **"Mere liye koi sarkari yojana hai?"** (Any government schemes for me?) |
| Agent | Checks eligibility based on profile (5 acres, wheat/rice, Haryana) and lists relevant schemes like PM-Kisan, PM Fasal Bima Yojana, etc. |

### Step 3 — Follow-up on Scheme
| Speaker | Says |
|---------|------|
| You | **"PM Kisan ke liye kaise apply karu?"** (How do I apply for PM Kisan?) |
| Agent | Explains the application process |

> **Talking point:** "The agent matched schemes to Ramesh's specific profile — his state, land holding, and crops. A farmer with different details would get different scheme recommendations."

### Step 4 — Weather Query
| Speaker | Says |
|---------|------|
| You | **"Kal mausam kaisa rahega?"** (How's the weather tomorrow?) |
| Agent | Fetches 5-day forecast for Karnal, Haryana and reports temperature, rain, and any alerts |

> **Talking point:** "Weather data comes from Open-Meteo — free, no API key needed, and it automatically used Ramesh's home district since he didn't specify a location."

### Step 5 — End Call
| Speaker | Says |
|---------|------|
| You | **"Bahut accha, shukriya"** (Very good, thanks) |
| Agent | Warm farewell, call disconnects automatically |

---

## What to Highlight

| Feature | How It Works |
|---------|-------------|
| **11 Indian languages** | Sarvam AI STT + TTS with language auto-detection |
| **No app needed** | Works over phone call (SIP) or browser (WebRTC) |
| **Live data** | Mandi prices from data.gov.in, weather from Open-Meteo |
| **45 government schemes** | Curated dataset covering 15 states, matched to farmer profile |
| **Persistent profiles** | PostgreSQL stores farmer data across calls |
| **Low latency** | STT < 500ms, LLM < 2s, TTS streaming — total < 3s round-trip |
| **Single EC2** | Everything runs on one t3.medium (~$35/month) |

## Before the Demo

1. **Clear the database** so onboarding starts fresh:
   ```bash
   ssh -i ~/.ssh/gramvaani_ec2 ubuntu@gramsaathi.in \
     "cd /opt/gram-sathi && sudo docker compose exec postgres \
      psql -U gramvaani -d gramvaani -c 'TRUNCATE users, call_logs, conversation_turns CASCADE;'"
   ```

2. **Open the dashboard** in a second tab: `https://gramsaathi.in:3000`
   - After Call 1, show the new user profile in **User Profiles**
   - After Call 2, show call history and conversation transcripts in **Call History**

3. **Check services are running:**
   ```bash
   ssh -i ~/.ssh/gramvaani_ec2 ubuntu@gramsaathi.in \
     "cd /opt/gram-sathi && sudo docker compose ps"
   ```
