terraform {
  backend "s3" {
    key = "petrocast/preview/terraform.tfstate"
    # bucket, region, dynamodb_table, encrypt from:
    # infra/terraform/backend.config (gitignored)
  }
}
