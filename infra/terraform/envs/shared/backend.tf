terraform {
  backend "s3" {
    key = "petrocast/shared/terraform.tfstate"
    # bucket, region, dynamodb_table, encrypt are read from:
    # infra/terraform/backend.config (gitignored)
    # See infra/terraform/backend.config.example
  }
}
