module "vpc" {
  source  = "../../modules/vpc"
  project = var.project
  cidr    = var.vpc_cidr
}

module "ecr" {
  source = "../../modules/ecr"
  name   = "${var.project}/mock-api"
}

module "route53" {
  source = "../../modules/route53"
  domain = var.domain
}

module "s3_artifacts" {
  source  = "../../modules/s3-artifacts"
  project = var.project
}

data "aws_s3_bucket" "tf_state" {
  bucket = var.tf_state_bucket_name
}

data "aws_dynamodb_table" "tf_locks" {
  name = var.tf_lock_table_name
}

module "iam_github_oidc" {
  source               = "../../modules/iam-github-oidc"
  github_repo          = var.github_repo
  ecr_repository_arn   = module.ecr.repository_arn
  artifacts_bucket_arn = module.s3_artifacts.artifacts_bucket_arn
  reports_bucket_arn   = module.s3_artifacts.reports_bucket_arn
  tf_state_bucket_arn  = data.aws_s3_bucket.tf_state.arn
  tf_lock_table_arn    = data.aws_dynamodb_table.tf_locks.arn
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
