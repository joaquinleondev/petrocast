terraform {
  backend "s3" {
    key = "petrocast/staging/terraform.tfstate"
    # bucket, region, use_lockfile, encrypt from:
    # infra/terraform/backend.config (gitignored)
  }
}
