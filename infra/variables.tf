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
