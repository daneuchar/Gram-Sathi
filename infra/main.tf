terraform {
  required_version = "~> 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "local" {
    path = "~/.terraform-states/gram-sathi/terraform.tfstate"
  }
}

provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}

# Latest Ubuntu 22.04 LTS AMI (Canonical)
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# SSH Key Pair
resource "aws_key_pair" "gram_sathi" {
  key_name   = "gram-sathi-key"
  public_key = file(pathexpand(var.ssh_public_key_path))

  lifecycle {
    ignore_changes = [public_key]
  }
}

# Security Group
resource "aws_security_group" "gram_sathi" {
  name        = "gram-sathi-sg"
  description = "Gram Sathi EC2 - allow dashboard, backend, LiveKit, SSH"

  ingress {
    description = "HTTP for nginx and Certbot"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.your_ip_cidr]
  }

  ingress {
    description = "dan ssh"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["49.206.48.68/32"]
  }

  ingress {
    description = "Next.js dashboard"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "LiveKit signaling (WebSocket)"
    from_port   = 7880
    to_port     = 7880
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "LiveKit ICE-TCP (WebRTC fallback)"
    from_port   = 7881
    to_port     = 7881
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "LiveKit media (RTP/UDP)"
    from_port   = 7882
    to_port     = 7882
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "FastAPI backend"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SIP signaling (UDP)"
    from_port   = 5060
    to_port     = 5060
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SIP signaling (TCP)"
    from_port   = 5060
    to_port     = 5060
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "RTP media"
    from_port   = 10000
    to_port     = 20000
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# IAM — trust policy (EC2 can assume this role)
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

# IAM — inline policy: read SSM params scoped to /gram-sathi/*
data "aws_iam_policy_document" "ssm_read" {
  statement {
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/gram-sathi/*"]
  }

  statement {
    actions   = ["kms:Decrypt"]
    resources = ["arn:aws:kms:${var.region}:${data.aws_caller_identity.current.account_id}:key/alias/aws/ssm"]
  }
}

resource "aws_iam_role" "gram_sathi" {
  name               = "gram-sathi-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
}

resource "aws_iam_role_policy" "ssm_read" {
  name   = "gram-sathi-ssm-read"
  role   = aws_iam_role.gram_sathi.id
  policy = data.aws_iam_policy_document.ssm_read.json
}

# Inline policy: only allow Bedrock inference (no create/delete/modify permissions)
data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = ["arn:aws:bedrock:${var.region}::foundation-model/*"]
  }
}

resource "aws_iam_role_policy" "bedrock_invoke" {
  name   = "gram-sathi-bedrock-invoke"
  role   = aws_iam_role.gram_sathi.id
  policy = data.aws_iam_policy_document.bedrock_invoke.json
}

data "aws_iam_policy_document" "translate" {
  statement {
    actions   = ["translate:TranslateText"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "translate" {
  name   = "gram-sathi-translate"
  role   = aws_iam_role.gram_sathi.id
  policy = data.aws_iam_policy_document.translate.json
}

resource "aws_iam_instance_profile" "gram_sathi" {
  name = "gram-sathi-instance-profile"
  role = aws_iam_role.gram_sathi.name
}

# SSM Parameters — fill real values before first boot:
#   aws ssm put-parameter --name /gram-sathi/sarvam_api_key --value "sk-..." \
#     --type SecureString --overwrite --region ap-south-1
#   aws ssm put-parameter --name /gram-sathi/data_gov_api_key --value "..." \
#     --type SecureString --overwrite --region ap-south-1

resource "aws_ssm_parameter" "sarvam_api_key" {
  name  = "/gram-sathi/sarvam_api_key"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    # Prevent Terraform from overwriting real values you set manually
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "data_gov_api_key" {
  name  = "/gram-sathi/data_gov_api_key"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "twilio_account_sid" {
  name  = "/gram-sathi/twilio_account_sid"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "twilio_auth_token" {
  name  = "/gram-sathi/twilio_auth_token"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "twilio_phone_number" {
  name  = "/gram-sathi/twilio_phone_number"
  type  = "String"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "indian_api_key" {
  name  = "/gram-sathi/indian_api_key"
  type  = "SecureString"
  value = "REPLACE_ME"

  lifecycle {
    ignore_changes = [value]
  }
}

locals {
  user_data = <<-EOF
    #!/usr/bin/env bash
    # All output logged — SSH and run: tail -f /var/log/gram-sathi-init.log
    exec > /var/log/gram-sathi-init.log 2>&1
    set -euo pipefail

    echo "=== [1/6] Installing Docker and dependencies ==="
    apt-get update -qq
    apt-get install -y -qq docker.io docker-compose-v2 git awscli
    systemctl enable --now docker

    echo "=== [2/6] Cloning repository ==="
    git clone https://github.com/daneuchar/Gram-Sathi.git /opt/gram-sathi
    cd /opt/gram-sathi

    echo "=== [3/6] Fetching secrets from SSM ==="
    SARVAM_KEY=$(aws ssm get-parameter \
      --name /gram-sathi/sarvam_api_key \
      --with-decryption \
      --query Parameter.Value \
      --output text \
      --region ${var.region})

    DATA_GOV_KEY=$(aws ssm get-parameter \
      --name /gram-sathi/data_gov_api_key \
      --with-decryption \
      --query Parameter.Value \
      --output text \
      --region ${var.region})

    TWILIO_SID=$(aws ssm get-parameter \
      --name /gram-sathi/twilio_account_sid \
      --with-decryption \
      --query Parameter.Value \
      --output text \
      --region ${var.region})

    TWILIO_TOKEN=$(aws ssm get-parameter \
      --name /gram-sathi/twilio_auth_token \
      --with-decryption \
      --query Parameter.Value \
      --output text \
      --region ${var.region})

    TWILIO_PHONE=$(aws ssm get-parameter \
      --name /gram-sathi/twilio_phone_number \
      --query Parameter.Value \
      --output text \
      --region ${var.region})

    INDIAN_KEY=$(aws ssm get-parameter \
      --name /gram-sathi/indian_api_key \
      --with-decryption \
      --query Parameter.Value \
      --output text \
      --region ${var.region})

    echo "=== [4/6] Setting public IP (Elastic IP) ==="
    PUBLIC_IP="${aws_eip.gram_sathi.public_ip}"

    echo "=== [5/6] Writing .env ==="
    printf '%s\n' \
      "AWS_DEFAULT_REGION=${var.region}" \
      "BEDROCK_REGION=ap-south-1" \
      "BEDROCK_MODEL_ID=global.amazon.nova-2-lite-v1:0" \
      "SARVAM_API_KEY=$SARVAM_KEY" \
      "DATA_GOV_API_KEY=$DATA_GOV_KEY" \
      "TWILIO_ACCOUNT_SID=$TWILIO_SID" \
      "TWILIO_AUTH_TOKEN=$TWILIO_TOKEN" \
      "TWILIO_PHONE_NUMBER=$TWILIO_PHONE" \
      "INDIAN_API_KEY=$INDIAN_KEY" \
      "DATABASE_URL=postgresql+asyncpg://gramvaani:gramvaani@postgres:5432/gramvaani" \
      "LIVEKIT_URL=ws://livekit:7880" \
      "LIVEKIT_API_KEY=devkey" \
      "LIVEKIT_API_SECRET=secret" \
      "DEBUG=false" \
      "PUBLIC_URL=http://$PUBLIC_IP:8000" \
      "LIVEKIT_PUBLIC_URL=ws://$PUBLIC_IP:7880" \
      > .env

    echo "=== [6/6] Running deploy.sh ==="
    bash deploy.sh

    echo "=== Boot complete ==="
  EOF
}

resource "aws_eip" "gram_sathi" {
  domain = "vpc"
  tags = {
    Name = "gram-sathi-eip"
  }
}

resource "aws_eip_association" "gram_sathi" {
  instance_id   = aws_instance.gram_sathi.id
  allocation_id = aws_eip.gram_sathi.id
}

# Route53 — gramsaathi.in DNS records
data "aws_route53_zone" "gram_sathi" {
  zone_id = "Z01893901H6C90D2WCVL"
}

resource "aws_route53_record" "apex" {
  zone_id = data.aws_route53_zone.gram_sathi.zone_id
  name    = "gramsaathi.in"
  type    = "A"
  ttl     = 300
  records = [aws_eip.gram_sathi.public_ip]
}

resource "aws_route53_record" "www" {
  zone_id = data.aws_route53_zone.gram_sathi.zone_id
  name    = "www.gramsaathi.in"
  type    = "A"
  ttl     = 300
  records = [aws_eip.gram_sathi.public_ip]
}

resource "aws_instance" "gram_sathi" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.medium"
  key_name               = aws_key_pair.gram_sathi.key_name
  vpc_security_group_ids = [aws_security_group.gram_sathi.id]
  iam_instance_profile   = aws_iam_instance_profile.gram_sathi.name
  user_data              = local.user_data

  root_block_device {
    volume_type = "gp3"
    volume_size = 20
  }

  tags = {
    Name = "gram-sathi"
  }

  lifecycle {
    ignore_changes = [user_data]
  }
}
