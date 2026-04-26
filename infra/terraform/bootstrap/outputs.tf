output "state_bucket" {
  value       = aws_s3_bucket.tf_state.bucket
  description = "S3 bucket for Terraform remote state"
}

output "lock_table" {
  value       = aws_dynamodb_table.tf_locks.name
  description = "DynamoDB table for Terraform state locking"
}

output "backend_config" {
  value       = <<-EOT
    # infra/terraform/backend.config
    bucket         = "${aws_s3_bucket.tf_state.bucket}"
    region         = "${var.aws_region}"
    dynamodb_table = "${aws_dynamodb_table.tf_locks.name}"
    encrypt        = true
  EOT
  description = "Paste this into infra/terraform/backend.config after bootstrap"
}
