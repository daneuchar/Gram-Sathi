#!/usr/bin/env bash
# Deploy Gram Sathi on a fresh Ubuntu EC2 instance (t3.medium, ap-south-1)
# Usage: ssh into EC2, then: curl -sL <raw-github-url>/deploy.sh | bash
#   OR: git clone the repo and run ./deploy.sh

set -euo pipefail

echo "=== Gram Sathi — EC2 Deployment ==="

# 1. Install Docker if not present
if ! command -v docker &>/dev/null; then
    echo "Installing Docker..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq docker.io docker-compose-plugin
    sudo usermod -aG docker "$USER"
    echo "Docker installed. You may need to log out and back in for group changes."
fi

# Ensure docker is running
sudo systemctl enable --now docker

# 2. Clone repo if not already in it
if [[ ! -f "docker-compose.yml" ]]; then
    if [[ -d "Gram-Sathi" ]]; then
        cd Gram-Sathi
    else
        echo "Cloning repository..."
        git clone https://github.com/daneuchar/Gram-Sathi.git
        cd Gram-Sathi
    fi
fi

# 3. Check .env exists
if [[ ! -f ".env" ]]; then
    echo ""
    echo "ERROR: .env file not found!"
    echo "Copy .env.example to .env and fill in your API keys:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    echo ""
    echo "Required keys: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, SARVAM_API_KEY, DATA_GOV_API_KEY"
    echo "Also set PUBLIC_URL and LIVEKIT_PUBLIC_URL to your EC2 public IP."
    exit 1
fi

# 4. Detect public IP and remind user
PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "UNKNOWN")
echo ""
echo "EC2 Public IP: $PUBLIC_IP"
echo "Make sure your .env has:"
echo "  PUBLIC_URL=http://$PUBLIC_IP:8000"
echo "  LIVEKIT_PUBLIC_URL=ws://$PUBLIC_IP:7880"
echo ""

# 5. Build and start all services
echo "Building and starting services..."
sudo docker compose up -d --build

echo ""
echo "=== Deployment complete ==="
echo ""
echo "Services:"
echo "  Dashboard:  http://$PUBLIC_IP:3000"
echo "  Backend:    http://$PUBLIC_IP:8000"
echo "  Test Call:  http://$PUBLIC_IP:8000/test"
echo "  LiveKit:    ws://$PUBLIC_IP:7880"
echo ""
echo "Logs:  sudo docker compose logs -f"
echo "Stop:  sudo docker compose down"
