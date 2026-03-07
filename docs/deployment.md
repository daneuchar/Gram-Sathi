# Gram Saathi — AWS Deployment Guide

Single EC2 instance running all services via Docker Compose. Designed for demo/hackathon use (up to 5 concurrent users).

## Architecture

```
              ┌──────────────────────────────────────────────┐
              │  EC2 t3.medium  (ap-south-1 / Mumbai)        │
              │                                              │
Farmer ──►    │  LiveKit Server     :7880 (ws), 7882 (udp)   │
Browser ──►   │  LiveKit Agent      (voice pipeline)         │
Dashboard ──► │  FastAPI Backend    :8000                     │
              │  Next.js Frontend   :3000                     │
              │  PostgreSQL         :5432                     │
              └──────────────────────────────────────────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
   AWS Bedrock     Sarvam AI      data.gov.in
   (Llama 3.3)    (STT + TTS)    (Mandi prices)
```

## Prerequisites

- AWS account with Bedrock access (Llama 3.3 70B enabled in ap-south-1)
- API keys: Sarvam AI, data.gov.in
- SSH key pair for EC2

## Step 1: Launch EC2

- **Instance type**: t3.medium (2 vCPU, 4GB RAM)
- **AMI**: Ubuntu 22.04 LTS
- **Region**: ap-south-1 (Mumbai)
- **Storage**: 20GB gp3
- **Security group** — inbound rules:

| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22 | TCP | Your IP | SSH |
| 3000 | TCP | 0.0.0.0/0 | Dashboard |
| 7880 | TCP | 0.0.0.0/0 | LiveKit signaling (WebSocket) |
| 7882 | UDP | 0.0.0.0/0 | LiveKit media (RTP audio) |
| 8000 | TCP | 0.0.0.0/0 | Backend API + test page |

## Step 2: SSH and Clone

```bash
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>

git clone https://github.com/daneuchar/Gram-Sathi.git
cd Gram-Sathi
```

## Step 3: Configure Environment

```bash
cp .env.example .env
nano .env
```

Fill in these required values:

```env
AWS_ACCESS_KEY_ID=<your-aws-key>
AWS_SECRET_ACCESS_KEY=<your-aws-secret>
AWS_DEFAULT_REGION=ap-south-1
SARVAM_API_KEY=<your-sarvam-key>
DATA_GOV_API_KEY=<your-data-gov-key>

# Set these to your EC2 public IP
PUBLIC_URL=http://<EC2_PUBLIC_IP>:8000
LIVEKIT_PUBLIC_URL=ws://<EC2_PUBLIC_IP>:7880
```

## Step 4: Deploy

```bash
./deploy.sh
```

This installs Docker (if needed), builds all images, and starts 5 services. First run takes 3-5 minutes to build.

## Step 5: Verify

| Service | URL | Check |
|---------|-----|-------|
| Dashboard | `http://<IP>:3000` | Should show overview page |
| Backend | `http://<IP>:8000/api/health` | Should return `{"status": "ok"}` |
| Test call | `http://<IP>:8000/test` | Opens voice test page |
| LiveKit | `ws://<IP>:7880` | Agent connects automatically |

## Commands

```bash
# View logs (all services)
sudo docker compose logs -f

# View logs (specific service)
sudo docker compose logs -f agent
sudo docker compose logs -f backend

# Restart everything
sudo docker compose restart

# Stop everything
sudo docker compose down

# Rebuild after code changes
git pull
sudo docker compose up -d --build

# Reset database (deletes all users and call history)
sudo docker compose down
sudo docker volume rm gram-sathi_pgdata
sudo docker compose up -d
```

## Services

| Service | Container | Port | Description |
|---------|-----------|------|-------------|
| postgres | postgres:15-alpine | 5432 | User profiles, call logs, conversation turns |
| livekit | livekit/livekit-server | 7880, 7882/udp | Real-time media server |
| backend | gram-sathi-backend | 8000 | REST API, dashboard endpoints, webhooks |
| agent | gram-sathi-agent | — | Voice pipeline: STT → LLM → TTS |
| frontend | gram-sathi-frontend | 3000 | Next.js dashboard |

## Troubleshooting

**Agent not connecting to LiveKit**
```bash
sudo docker compose logs agent | grep "connected"
```
Check that LIVEKIT_URL is `ws://livekit:7880` (internal Docker network). The agent connects to LiveKit via the Docker network, not the public IP.

**Voice test page not working**
- Ensure ports 7880 (TCP) and 7882 (UDP) are open in the security group
- Browser needs microphone permission
- Check LIVEKIT_PUBLIC_URL in .env matches `ws://<EC2_PUBLIC_IP>:7880`

**No audio / TTS silent**
```bash
sudo docker compose logs agent | grep "sarvam\|tts_node"
```
Verify SARVAM_API_KEY is set correctly in .env.

**Tool calls failing**
```bash
sudo docker compose logs agent | grep "bedrock\|tool"
```
Verify AWS credentials and that Llama 3.3 is enabled in your Bedrock console for ap-south-1.

## Cost Estimate

| Resource | Cost/month | Notes |
|----------|-----------|-------|
| EC2 t3.medium | ~$30 | On-demand, ap-south-1 |
| EBS 20GB gp3 | ~$2 | Storage |
| Bedrock Llama 3.3 | Pay per token | ~$0.001/call |
| Sarvam AI | Pay per minute | ~$0.01/min STT+TTS |
| **Total (light demo use)** | **~$35-40/month** | |

For hackathon: use a spot instance ($10/month) or stop the instance when not demoing.
