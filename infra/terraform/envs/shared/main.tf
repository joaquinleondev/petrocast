module "vpc" {
  source  = "../../modules/vpc"
  project = var.project
  cidr    = var.vpc_cidr
}

module "ecr" {
  source = "../../modules/ecr"
  name   = "${var.project}/mock-api"
}

# Dagster/data image for the Phase-2 data stack (built by build-data.yml).
module "ecr_data" {
  source = "../../modules/ecr"
  name   = "${var.project}/data"
}

module "route53" {
  source = "../../modules/route53"
  domain = var.domain
}

module "s3_artifacts" {
  source  = "../../modules/s3-artifacts"
  project = var.project
}

# MLflow artifact store + laptop IAM user (ADR-0032, F3-08). Backend store is
# Postgres in the cloud (Supabase/Neon), out of Terraform's scope.
module "s3_mlflow" {
  source  = "../../modules/s3-mlflow"
  project = var.project
}

data "aws_s3_bucket" "tf_state" {
  bucket = var.tf_state_bucket_name
}

module "iam_github_oidc" {
  source                         = "../../modules/iam-github-oidc"
  github_repo                    = var.github_repo
  ecr_repository_arn             = module.ecr.repository_arn
  additional_ecr_repository_arns = [module.ecr_data.repository_arn]
  artifacts_bucket_arn           = module.s3_artifacts.artifacts_bucket_arn
  reports_bucket_arn             = module.s3_artifacts.reports_bucket_arn
  tf_state_bucket_arn            = data.aws_s3_bucket.tf_state.arn
}

module "cloudwatch" {
  source  = "../../modules/cloudwatch"
  project = var.project
}

# Upload Swarm stack templates to S3 so EC2 user-data can download them at boot
resource "aws_s3_object" "traefik_http01_stack" {
  bucket = module.s3_artifacts.artifacts_bucket
  key    = "swarm/traefik.http01.stack.yml"
  source = "${path.module}/../../../swarm/traefik.http01.stack.yml"
  etag   = filemd5("${path.module}/../../../swarm/traefik.http01.stack.yml")
}

resource "aws_s3_object" "traefik_dns01_stack" {
  bucket = module.s3_artifacts.artifacts_bucket
  key    = "swarm/traefik.dns01.stack.yml"
  source = "${path.module}/../../../swarm/traefik.dns01.stack.yml"
  etag   = filemd5("${path.module}/../../../swarm/traefik.dns01.stack.yml")
}

resource "aws_s3_object" "mock_api_stack" {
  bucket = module.s3_artifacts.artifacts_bucket
  key    = "swarm/mock-api.stack.yml"
  source = "${path.module}/../../../swarm/mock-api.stack.yml"
  etag   = filemd5("${path.module}/../../../swarm/mock-api.stack.yml")
}

resource "aws_s3_object" "deploy_script" {
  bucket = module.s3_artifacts.artifacts_bucket
  key    = "scripts/deploy.sh"
  source = "${path.module}/../../../scripts/deploy.sh"
  etag   = filemd5("${path.module}/../../../scripts/deploy.sh")
}

resource "aws_s3_object" "rollback_script" {
  bucket = module.s3_artifacts.artifacts_bucket
  key    = "scripts/rollback.sh"
  source = "${path.module}/../../../scripts/rollback.sh"
  etag   = filemd5("${path.module}/../../../scripts/rollback.sh")
}

resource "aws_s3_object" "deploy_data_script" {
  bucket = module.s3_artifacts.artifacts_bucket
  key    = "scripts/deploy-data.sh"
  source = "${path.module}/../../../scripts/deploy-data.sh"
  etag   = filemd5("${path.module}/../../../scripts/deploy-data.sh")
}

# Phase-2 data stack bundle — pulled to /opt/petrocast/ by the staging bootstrap.
# Relative paths (mirrored under the "stack/" S3 prefix) so the compose bind
# mounts (e.g. ./data/postgres/init) resolve on the host.
locals {
  data_stack_artifacts = [
    "compose.data.yml",
    "compose.datahub.yml",
    "compose.dev.yml",
    "compose.staging.yml",
    "data/postgres/init/001-create-medallion-schemas.sql",
    "data/postgres/init/002-create-bi-readonly-role.sh",
    "metabase/provision_metabase.py",
    "datahub/datahub.sh",
    "datahub/recipes/dbt.yml",
    "datahub/recipes/postgres.yml",
  ]
}

resource "aws_s3_object" "data_stack" {
  for_each = toset(local.data_stack_artifacts)
  bucket   = module.s3_artifacts.artifacts_bucket
  key      = "stack/${each.value}"
  source   = "${path.module}/../../../${each.value}"
  etag     = filemd5("${path.module}/../../../${each.value}")
}
