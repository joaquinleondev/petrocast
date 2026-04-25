output "oidc_provider_arn" {
  value       = aws_iam_openid_connect_provider.github.arn
  description = "ARN of the GitHub OIDC provider"
}

output "ci_role_arn" {
  value       = aws_iam_role.ci.arn
  description = "ARN of the CI role (for lint, test, build, scan jobs)"
}

output "deploy_role_arn" {
  value       = aws_iam_role.deploy.arn
  description = "ARN of the deploy role (for SSM Run Command + ECR retag)"
}
