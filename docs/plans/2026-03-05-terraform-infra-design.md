# Gram Sathi — Terraform Infrastructure Design

**Date:** 2026-03-05
**Scope:** Single EC2 deployment on AWS (ap-south-1), fully automated boot via SSM Parameter Store

## Architecture

Single t3.medium EC2 instance running all services via Docker Compose. Secrets fetched from SSM at boot — no manual `.env` editing required.

## Resources

| Resource | Details |
|---|---|
| `aws_security_group` | Ports 22 (your IP), 3000, 7880, 8000 TCP; 7882 UDP open to 0.0.0.0/0 |
| `aws_iam_policy` | `ssm:GetParameter` on `/gram-sathi/*` + `AmazonBedrockFullAccess` |
| `aws_iam_role` | EC2 assume-role trust policy |
| `aws_iam_instance_profile` | Attaches role to EC2 |
| `aws_ssm_parameter` | `/gram-sathi/sarvam_api_key` and `/gram-sathi/data_gov_api_key` as SecureString with value `REPLACE_ME` |
| `aws_key_pair` | Uploads local SSH public key |
| `aws_instance` | t3.medium, Ubuntu 22.04 LTS, 20GB gp3, instance profile attached, user data script |

## IAM Permissions

- Bedrock: `AmazonBedrockFullAccess` managed policy — allows calling Llama 3.3 in ap-south-1 without static AWS keys
- SSM: inline policy scoped to `/gram-sathi/*` parameters only

No `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` needed in `.env`.

## SSM Parameters

```
/gram-sathi/sarvam_api_key     SecureString  "REPLACE_ME"
/gram-sathi/data_gov_api_key   SecureString  "REPLACE_ME"
```

Fill actual values via AWS Console or CLI before first boot:
```bash
aws ssm put-parameter --name /gram-sathi/sarvam_api_key --value "sk-..." --type SecureString --overwrite
aws ssm put-parameter --name /gram-sathi/data_gov_api_key --value "..." --type SecureString --overwrite
```

## User Data Boot Sequence

1. `apt install docker docker-compose-plugin`
2. `git clone https://github.com/daneuchar/Gram-Sathi.git`
3. Fetch SSM params via `aws ssm get-parameter --with-decryption`
4. Detect public IP from EC2 metadata service
5. Write complete `.env` file
6. Run `./deploy.sh` — builds and starts all 5 containers

## File Structure

```
infra/
├── main.tf                   # provider, EC2, SG, IAM, SSM params
├── variables.tf              # region, your_ip_cidr, ssh_public_key_path
├── outputs.tf                # public IP, SSH command, service URLs
└── terraform.tfvars.example  # template for variables
```

## Variables

| Variable | Description | Default |
|---|---|---|
| `region` | AWS region | `ap-south-1` |
| `your_ip_cidr` | Your IP for SSH access (e.g. `1.2.3.4/32`) | — |
| `ssh_public_key_path` | Path to your `.pub` key file | `~/.ssh/id_rsa.pub` |

## Outputs

- `instance_public_ip` — EC2 public IP
- `ssh_command` — ready-to-run SSH command
- `dashboard_url`, `backend_url`, `livekit_url` — service URLs
