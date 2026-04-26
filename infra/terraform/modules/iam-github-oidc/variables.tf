variable "github_repo" {
  type        = string
  description = "GitHub repo in org/repo format, e.g. joaquinleondev/petrocast"
}

variable "ecr_repository_arn" {
  type        = string
  description = "ARN of the ECR repository to grant push access"
}

variable "artifacts_bucket_arn" {
  type        = string
  description = "ARN of the pipeline artifacts S3 bucket"
}

variable "reports_bucket_arn" {
  type        = string
  description = "ARN of the test reports S3 bucket"
}

variable "tf_state_bucket_arn" {
  type        = string
  description = "ARN of the Terraform remote state S3 bucket — granted to ci-role for tf-plan jobs and S3 lockfiles"
}

variable "tags" {
  type    = map(string)
  default = {}
}
