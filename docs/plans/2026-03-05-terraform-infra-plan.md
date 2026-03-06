# Terraform Infrastructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Provision a single EC2 t3.medium on AWS (ap-south-1) with Docker Compose services starting automatically at boot, secrets pulled from SSM Parameter Store.

**Architecture:** Terraform declares EC2, security group, IAM role (Bedrock + SSM access), and SSM placeholder parameters. A user data script on the instance fetches secrets, writes `.env`, and runs `./deploy.sh` — no manual steps after `terraform apply`.

**Tech Stack:** Terraform ~> 5.0 AWS provider, AWS EC2, IAM, SSM Parameter Store, Ubuntu 22.04 LTS

---

### Task 1: Create infra/variables.tf

**Files:**
- Create: `infra/variables.tf`

**Step 1: Create the infra directory and write variables.tf**

```hcl
# infra/variables.tf

variable "region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-south-1"
}

variable "your_ip_cidr" {
  description = "Your public IP in CIDR notation for SSH access (e.g. 203.0.113.5/32)"
  type        = string
}

variable "ssh_public_key_path" {
  description = "Path to your SSH public key file uploaded to AWS as a key pair"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}
```

**Step 2: Verify file is valid HCL**

```bash
cd infra
terraform fmt variables.tf
```
Expected: no output (file already formatted) or reformatted file.

**Step 3: Commit**

```bash
git add infra/variables.tf
git commit -m "infra: add variables.tf"
```

---

### Task 2: Create infra/main.tf — provider, AMI data source, security group, IAM

**Files:**
- Create: `infra/main.tf`

**Step 1: Write provider and AMI data source**

```hcl
# infra/main.tf

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
```

**Step 2: Append SSH key pair resource**

```hcl
# SSH Key Pair
resource "aws_key_pair" "gram_sathi" {
  key_name   = "gram-sathi-key"
  public_key = file(var.ssh_public_key_path)
}
```

**Step 3: Append security group**

```hcl
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
```

**Step 4: Append IAM role, policies, instance profile**

```hcl
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
```

**Step 5: Commit**

```bash
git add infra/main.tf
git commit -m "infra: add provider, AMI data source, SG, IAM"
```

---

### Task 3: Add SSM parameters + EC2 instance to main.tf

**Files:**
- Modify: `infra/main.tf` (append)

**Step 1: Append SSM placeholder parameters**

```hcl
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
```

**Step 2: Append user data local and EC2 instance**

```hcl
locals {
  user_data = <<-EOF
    #!/usr/bin/env bash
    set -euo pipefail
    # All output logged — SSH and run: tail -f /var/log/gram-sathi-init.log
    exec > /var/log/gram-sathi-init.log 2>&1

    echo "=== [1/6] Installing Docker and dependencies ==="
    apt-get update -qq
    apt-get install -y -qq docker.io docker-compose-plugin git awscli
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

    echo "=== [4/6] Detecting public IP ==="
    PUBLIC_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4)

    echo "=== [5/6] Writing .env ==="
    cat > .env <<ENVEOF
    AWS_DEFAULT_REGION=${var.region}
    BEDROCK_MODEL_ID=us.meta.llama3-3-70b-instruct-v1:0
    SARVAM_API_KEY=$SARVAM_KEY
    DATA_GOV_API_KEY=$DATA_GOV_KEY
    DATABASE_URL=postgresql+asyncpg://gramvaani:gramvaani@postgres:5432/gramvaani
    LIVEKIT_URL=ws://livekit:7880
    LIVEKIT_API_KEY=devkey
    LIVEKIT_API_SECRET=secret
    DEBUG=false
    PUBLIC_URL=http://$PUBLIC_IP:8000
    LIVEKIT_PUBLIC_URL=ws://$PUBLIC_IP:7880
    ENVEOF

    echo "=== [6/6] Running deploy.sh ==="
    bash deploy.sh

    echo "=== Boot complete ==="
  EOF
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
}
```

**Step 3: Commit**

```bash
git add infra/main.tf
git commit -m "infra: add SSM parameters and EC2 instance with user data"
```

---

### Task 4: Create infra/outputs.tf and terraform.tfvars.example

**Files:**
- Create: `infra/outputs.tf`
- Create: `infra/terraform.tfvars.example`

**Step 1: Write outputs.tf**

```hcl
# infra/outputs.tf

output "instance_public_ip" {
  description = "EC2 public IP address"
  value       = aws_instance.gram_sathi.public_ip
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "ssh -i ${trimsuffix(var.ssh_public_key_path, ".pub")} ubuntu@${aws_instance.gram_sathi.public_ip}"
}

output "dashboard_url" {
  description = "Next.js dashboard"
  value       = "http://${aws_instance.gram_sathi.public_ip}:3000"
}

output "backend_url" {
  description = "FastAPI backend + health check"
  value       = "http://${aws_instance.gram_sathi.public_ip}:8000/api/health"
}

output "test_call_url" {
  description = "Voice test page"
  value       = "http://${aws_instance.gram_sathi.public_ip}:8000/test"
}

output "livekit_url" {
  description = "LiveKit signaling endpoint"
  value       = "ws://${aws_instance.gram_sathi.public_ip}:7880"
}

output "init_log_command" {
  description = "SSH command to watch boot progress in real time"
  value       = "ssh -i ${trimsuffix(var.ssh_public_key_path, ".pub")} ubuntu@${aws_instance.gram_sathi.public_ip} 'tail -f /var/log/gram-sathi-init.log'"
}
```

**Step 2: Write terraform.tfvars.example**

```hcl
# infra/terraform.tfvars.example
# Copy to terraform.tfvars and fill in your values:
#   cp terraform.tfvars.example terraform.tfvars

region              = "ap-south-1"
your_ip_cidr        = "YOUR_PUBLIC_IP/32"   # find it: curl ifconfig.me
ssh_public_key_path = "~/.ssh/id_rsa.pub"
```

**Step 3: Add terraform.tfvars to .gitignore (contains your IP)**

```bash
echo "infra/terraform.tfvars" >> .gitignore
echo "infra/.terraform/" >> .gitignore
echo "infra/.terraform.lock.hcl" >> .gitignore
echo "infra/terraform.tfstate*" >> .gitignore
```

**Step 4: Commit**

```bash
git add infra/outputs.tf infra/terraform.tfvars.example .gitignore
git commit -m "infra: add outputs, tfvars example, gitignore"
```

---

### Task 5: Validate with terraform init + validate + plan

**Files:** none — validation only

**Step 1: Install Terraform if not present**

```bash
# macOS
brew install terraform

# or download from https://developer.terraform.io/downloads
terraform version
```
Expected: `Terraform v1.x.x`

**Step 2: Initialise**

```bash
cd infra
terraform init
```
Expected: `Terraform has been successfully initialized!`

**Step 3: Format check**

```bash
terraform fmt -check -recursive
```
Expected: no output (all files formatted). If files are listed, run `terraform fmt` to fix.

**Step 4: Validate**

```bash
terraform validate
```
Expected: `Success! The configuration is valid.`

**Step 5: Create tfvars and dry-run plan**

```bash
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: set your_ip_cidr and ssh_public_key_path
terraform plan
```
Expected: plan showing ~9 resources to add, 0 to change, 0 to destroy.

Key things to check in the plan output:
- `aws_instance.gram_sathi` — instance_type = "t3.medium", root_block_device volume_size = 20
- `aws_security_group.gram_sathi` — 5 ingress rules present
- `aws_ssm_parameter.sarvam_api_key` and `aws_ssm_parameter.data_gov_api_key` — type = SecureString

**Step 6: Fill in real SSM values before applying**

```bash
aws ssm put-parameter \
  --name /gram-sathi/sarvam_api_key \
  --value "your-real-sarvam-key" \
  --type SecureString \
  --overwrite \
  --region ap-south-1

aws ssm put-parameter \
  --name /gram-sathi/data_gov_api_key \
  --value "your-real-data-gov-key" \
  --type SecureString \
  --overwrite \
  --region ap-south-1
```

Note: Do this BEFORE `terraform apply` so the user data script can fetch real values on first boot. The `lifecycle { ignore_changes = [value] }` block means Terraform won't overwrite these with `REPLACE_ME` on subsequent applies.

**Step 7: Apply**

```bash
terraform apply
```
Type `yes` when prompted. Takes ~2 minutes to provision EC2.

**Step 8: Watch boot progress**

```bash
# Terraform will print this after apply
$(terraform output -raw init_log_command)
```
Expected final line: `=== Boot complete ===` (takes 3-5 min for Docker build)

**Step 9: Verify services**

```bash
# Health check
curl $(terraform output -raw backend_url)
# Expected: {"status": "ok"}

# Dashboard
open $(terraform output -raw dashboard_url)
```

**Step 10: Commit final state**

```bash
cd ..
git add infra/
git commit -m "infra: complete Terraform configuration validated"
```

---

## Teardown

```bash
cd infra
terraform destroy
```
This terminates the EC2 and deletes the SG, IAM role, key pair, and SSM parameters. The SSM parameter values (real secrets) are deleted too — back them up first if needed.

## Cost Reminder

~$30/month for t3.medium on-demand. Stop the instance when not demoing:
```bash
aws ec2 stop-instances --instance-ids $(terraform output -raw instance_id) --region ap-south-1
```
(Add `instance_id` to outputs.tf if you want this convenience.)
