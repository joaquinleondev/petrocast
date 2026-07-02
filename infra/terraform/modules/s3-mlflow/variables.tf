variable "project" {
  type        = string
  description = "Project name used for bucket naming (bucket is <project>-ml-artifacts)"
}

variable "artifact_prefix" {
  type        = string
  default     = "mlflow"
  description = "Key prefix under which MLflow stores artifacts (s3://<bucket>/<prefix>)"
}

variable "create_iam_user" {
  type        = bool
  default     = true
  description = <<-EOT
    Create a dedicated, bucket-scoped IAM user + access key for team members
    running MLflow from their laptops. The secret access key lands in Terraform
    state (encrypted S3 backend) and is exposed as a sensitive output. Set to
    false to manage credentials manually (e.g. mint the key by hand in the
    console to keep it out of state).
  EOT
}

variable "noncurrent_version_expiration_days" {
  type        = number
  default     = 30
  description = "Delete NONCURRENT object versions after N days. Current versions (live model artifacts) never expire."
}

variable "force_destroy" {
  type        = bool
  default     = true
  description = "Allow `terraform destroy` to remove a non-empty bucket. Default true — tracking artifacts are regenerable (ADR-0032)."
}

variable "tags" {
  type    = map(string)
  default = {}
}
