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
  type = string
  # Core serving set only: API + warehouse. Orchestration/catalog/BI (Dagster,
  # DataHub, Metabase) run locally in Phase 3, so the box stays small (matches
  # preview/prod). Bump to t3.xlarge + DATA_STACK_PROFILE=full to run it all here.
  default = "t3.small"
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
