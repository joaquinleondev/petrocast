terraform {
  backend "s3" {
    key = "petrocast/staging/terraform.tfstate"
    # bucket, region, dynamodb_table, encrypt from:
    # infra/terraform/backend.config (gitignored)
  }
}
