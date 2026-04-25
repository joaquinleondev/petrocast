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
