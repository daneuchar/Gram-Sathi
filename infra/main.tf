terraform {
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
    resources = ["arn:aws:ssm:${var.region}:*:parameter/gram-sathi/*"]
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

# Attach AWS-managed Bedrock policy — lets the agent call Llama 3.3 without static keys
resource "aws_iam_role_policy_attachment" "bedrock" {
  role       = aws_iam_role.gram_sathi.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockFullAccess"
}

resource "aws_iam_instance_profile" "gram_sathi" {
  name = "gram-sathi-instance-profile"
  role = aws_iam_role.gram_sathi.name
}
