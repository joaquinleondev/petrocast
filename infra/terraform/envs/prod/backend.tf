terraform {
  backend "s3" {
    key = "petrocast/prod/terraform.tfstate"
    # bucket, region, dynamodb_table, encrypt from:
    # infra/terraform/backend.config (gitignored)
  }
}
