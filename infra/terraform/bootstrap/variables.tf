variable "aws_region" {
  type    = string
  default = "us-east-2"
}

variable "project" {
  type    = string
  default = "petrocast"
}

variable "force_destroy_state_bucket" {
  type        = bool
  default     = false
  description = "When true, Terraform deletes all object versions and delete markers before destroying the state bucket. Use only when intentionally tearing down bootstrap state."
}
