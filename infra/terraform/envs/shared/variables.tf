variable "project" {
  type    = string
  default = "petrocast"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "domain" {
  type    = string
  default = "petrocast.shop"
}

variable "github_repo" {
  type    = string
  default = "joaquinleondev/petrocast"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "tf_state_bucket_name" {
  type        = string
  description = "Terraform remote state S3 bucket name (output of bootstrap) — granted read to ci-role"
}

variable "tf_lock_table_name" {
  type        = string
  description = "Terraform DynamoDB lock table name (output of bootstrap) — granted access to ci-role"
}
