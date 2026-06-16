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

output "data_volume_id" {
  value       = length(aws_ebs_volume.data) > 0 ? aws_ebs_volume.data[0].id : ""
  description = "EBS data volume ID (empty when no data volume) — snapshot this before destroy"
}
