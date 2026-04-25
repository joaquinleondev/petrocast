output "log_group_names" {
  value       = { for k, v in aws_cloudwatch_log_group.this : k => v.name }
  description = "Map of log group keys to CloudWatch log group names"
}
