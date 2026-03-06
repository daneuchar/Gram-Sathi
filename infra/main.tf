terraform {
  required_version = "~> 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
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
}

# Security Group
resource "aws_security_group" "gram_sathi" {
  name        = "gram-sathi-sg"
  description = "Gram Sathi EC2 — allow dashboard, backend, LiveKit, SSH"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.your_ip_cidr]
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

resource "aws_iam_instance_profile" "gram_sathi" {
  name = "gram-sathi-instance-profile"
  role = aws_iam_role.gram_sathi.name
}
