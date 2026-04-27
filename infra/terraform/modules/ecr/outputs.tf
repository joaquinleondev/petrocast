output "repository_url" {
  value       = aws_ecr_repository.this.repository_url
  description = "Full URI of the ECR repository"
}

output "repository_arn" {
  value       = aws_ecr_repository.this.arn
  description = "ARN of the ECR repository"
}

output "registry_id" {
  value       = aws_ecr_repository.this.registry_id
  description = "AWS account ID (registry ID)"
}
