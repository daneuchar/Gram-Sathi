# infra/outputs.tf

output "instance_public_ip" {
  description = "EC2 public IP address"
  value       = aws_instance.gram_sathi.public_ip
}

output "instance_id" {
  description = "EC2 instance ID (useful for stop/start commands)"
  value       = aws_instance.gram_sathi.id
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "ssh -i ${var.ssh_private_key_path} ubuntu@${aws_instance.gram_sathi.public_ip}"
}

output "dashboard_url" {
  description = "Next.js dashboard"
  value       = "http://${aws_instance.gram_sathi.public_ip}:3000"
}

output "backend_url" {
  description = "FastAPI backend health check"
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
  value       = "ssh -i ${var.ssh_private_key_path} ubuntu@${aws_instance.gram_sathi.public_ip} 'tail -f /var/log/gram-sathi-init.log'"
}
