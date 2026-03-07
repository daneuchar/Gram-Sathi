# SIP Setup Guide — Twilio Missed Call Callback

One-time setup to enable the missed call → callback flow.

## 1. Twilio Phone Number Configuration

In [Twilio Console](https://console.twilio.com/) → Phone Numbers → Manage → Active Numbers → select your number:

- **Voice Configuration:**
  - "A call comes in" → **Webhook** → `https://gramsaathi.in/webhooks/missed-call` (HTTP POST)
  - "Call status changes" → `https://gramsaathi.in/webhooks/call-status` (HTTP POST)

This makes Twilio hit our webhook on every incoming call. Our webhook rejects the call immediately (farmer pays nothing) and triggers a SIP callback.

## 2. EC2 Security Group — Open SIP/RTP Ports

In AWS Console → EC2 → Security Groups → select the instance's security group → Inbound Rules:

| Type | Port Range | Source | Description |
|------|-----------|--------|-------------|
| Custom UDP | 5060 | 0.0.0.0/0 | SIP signaling |
| Custom TCP | 5060 | 0.0.0.0/0 | SIP signaling |
| Custom UDP | 10000-20000 | 0.0.0.0/0 | RTP media (voice audio) |

## 3. Set PUBLIC_IP in .env

LiveKit needs to know the server's public IP for SIP/RTP to work:

```bash
# On the EC2 instance
echo "PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)" >> /opt/gram-sathi/.env
```

## 4. Deploy

```bash
ssh -i ~/.ssh/gramvaani_ec2 ubuntu@gramsaathi.in \
  "cd /opt/gram-sathi && sudo docker compose up -d --build"
```

## 5. Verify

```bash
# Check LiveKit SIP is listening
ssh -i ~/.ssh/gramvaani_ec2 ubuntu@gramsaathi.in \
  "cd /opt/gram-sathi && sudo docker compose logs livekit | grep -i sip"

# Check backend started with webhooks
ssh -i ~/.ssh/gramvaani_ec2 ubuntu@gramsaathi.in \
  "cd /opt/gram-sathi && sudo docker compose logs backend | tail -20"
```

## 6. Test

1. Call the Twilio number from any phone
2. Let it ring once, then hang up (or wait — it auto-rejects)
3. Within 3-5 seconds, you should receive a callback
4. The Gram Saathi agent will greet you

## Troubleshooting

**No callback received:**
- Check backend logs: `sudo docker compose logs --tail=50 backend` — look for `[missed-call]` and `[callback]` entries
- Check LiveKit logs: `sudo docker compose logs --tail=50 livekit` — look for SIP errors
- Verify security group has ports 5060 and 10000-20000 open
- Verify PUBLIC_IP is set correctly in .env

**Call connects but no audio:**
- RTP ports (10000-20000/UDP) may be blocked — check security group
- Verify `PUBLIC_IP` matches the EC2 instance's actual public IP

**SIP trunk creation fails:**
- Check Twilio credentials in .env (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
- Check LiveKit logs for trunk creation errors
