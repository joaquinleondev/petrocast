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
  default = "t3.xlarge" # runs the API + full Phase-2 data stack (incl. DataHub)
}

variable "data_snapshot_id" {
  type        = string
  default     = ""
  description = "EBS snapshot ID to restore the data volume from when re-creating staging. Empty = blank volume."
}

variable "traefik_acme_email" {
  type        = string
  description = "Email for Let's Encrypt account registration"
}

variable "state_bucket" {
  type        = string
  description = "S3 bucket name for Terraform remote state (from bootstrap output)"
}
