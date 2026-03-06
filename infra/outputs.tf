# infra/outputs.tf

output "instance_public_ip" {
  description = "Elastic IP address (stable across stop/start)"
  value       = aws_eip.gram_sathi.public_ip
}

output "instance_id" {
  description = "EC2 instance ID (useful for stop/start commands)"
  value       = aws_instance.gram_sathi.id
}

output "domain" {
  description = "Primary domain"
  value       = "https://gramsaathi.in"
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "ssh -i ${var.ssh_private_key_path} ubuntu@${aws_eip.gram_sathi.public_ip}"
}

output "dashboard_url" {
  description = "Next.js dashboard"
  value       = "https://gramsaathi.in"
}

output "backend_url" {
  description = "FastAPI backend health check"
  value       = "https://gramsaathi.in/api/health"
}

output "test_call_url" {
  description = "Voice test page"
  value       = "https://gramsaathi.in/test"
}

output "livekit_url" {
  description = "LiveKit signaling endpoint"
  value       = "wss://gramsaathi.in/livekit/"
}

output "init_log_command" {
  description = "SSH command to watch boot progress in real time"
  value       = "ssh -i ${var.ssh_private_key_path} ubuntu@${aws_eip.gram_sathi.public_ip} 'tail -f /var/log/gram-sathi-init.log'"
}
