output "vpc_id" {
  value       = module.vpc.vpc_id
  description = "VPC ID shared by all envs"
}

output "public_subnet_ids" {
  value       = module.vpc.public_subnet_ids
  description = "Public subnet IDs (one per AZ)"
}

output "ecr_repository_url" {
  value       = module.ecr.repository_url
  description = "Full ECR repository URI — use in IMAGE_URI var"
}

output "ecr_registry_id" {
  value       = module.ecr.registry_id
  description = "AWS account ID (ECR registry)"
}

output "route53_zone_id" {
  value       = module.route53.zone_id
  description = "Route 53 hosted zone ID — used by env roots for DNS records"
}

output "route53_nameservers" {
  value       = module.route53.nameservers
  description = "NS records to configure at domain registrar (petrocast.shop)"
}

output "ci_role_arn" {
  value       = module.iam_github_oidc.ci_role_arn
  description = "ARN for CI_ROLE_ARN GitHub repo secret"
}

output "deploy_role_arn" {
  value       = module.iam_github_oidc.deploy_role_arn
  description = "ARN for DEPLOY_ROLE_ARN GitHub environment secret"
}

output "artifacts_bucket" {
  value       = module.s3_artifacts.artifacts_bucket
  description = "Pipeline artifacts bucket name"
}

output "reports_bucket" {
  value       = module.s3_artifacts.reports_bucket
  description = "Test reports bucket name"
}

output "cloudwatch_log_groups" {
  value       = module.cloudwatch.log_group_names
  description = "All CloudWatch log group names"
}
