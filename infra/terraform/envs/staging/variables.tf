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

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "traefik_acme_email" {
  type        = string
  description = "Email for Let's Encrypt account registration"
}

variable "state_bucket" {
  type        = string
  description = "S3 bucket name for Terraform remote state (from bootstrap output)"
}
