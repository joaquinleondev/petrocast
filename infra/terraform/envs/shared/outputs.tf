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

output "artifacts_bucket_arn" {
  value       = module.s3_artifacts.artifacts_bucket_arn
  description = "Pipeline artifacts bucket ARN — used by EC2 instance profile"
}

output "reports_bucket" {
  value       = module.s3_artifacts.reports_bucket
  description = "Test reports bucket name"
}

output "mlflow_artifacts_bucket" {
  value       = module.s3_mlflow.bucket
  description = "MLflow artifacts bucket name"
}

output "mlflow_artifact_root" {
  value       = module.s3_mlflow.artifact_root
  description = "PETROCAST_MLFLOW_ARTIFACT_ROOT — MLflow --default-artifact-root"
}

output "mlflow_iam_access_key_id" {
  value       = module.s3_mlflow.iam_access_key_id
  description = "AWS_ACCESS_KEY_ID for the MLflow artifacts IAM user"
}

output "mlflow_iam_secret_access_key" {
  value       = module.s3_mlflow.iam_secret_access_key
  sensitive   = true
  description = "AWS_SECRET_ACCESS_KEY for the MLflow artifacts IAM user — `terraform output -raw mlflow_iam_secret_access_key`"
}

output "cloudwatch_log_groups" {
  value       = module.cloudwatch.log_group_names
  description = "All CloudWatch log group names"
}
