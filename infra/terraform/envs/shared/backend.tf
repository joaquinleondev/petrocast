terraform {
  backend "s3" {
    key = "petrocast/shared/terraform.tfstate"
    # bucket, region, use_lockfile, encrypt are read from:
    # infra/terraform/backend.config (gitignored)
    # See infra/terraform/backend.config.example
  }
}
