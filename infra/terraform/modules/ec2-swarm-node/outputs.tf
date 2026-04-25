output "instance_id" {
  value       = aws_instance.this.id
  description = "EC2 instance ID (used in SSM Run Command)"
}

output "public_ip" {
  value       = aws_eip.this.public_ip
  description = "Static public IP (EIP) of the node"
}

output "security_group_id" {
  value       = aws_security_group.this.id
  description = "Security group ID"
}
