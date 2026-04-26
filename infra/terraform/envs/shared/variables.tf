variable "project" {
  type    = string
  default = "petrocast"
}

variable "aws_region" {
  type    = string
  default = "us-east-2"
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
  description = "Terraform remote state S3 bucket name (output of bootstrap) — grants state read and lockfile access to ci-role"
}
