terraform {
  backend "s3" {
    key = "petrocast/preview/terraform.tfstate"
    # bucket, region, use_lockfile, encrypt from:
    # infra/terraform/backend.config (gitignored)
  }
}
