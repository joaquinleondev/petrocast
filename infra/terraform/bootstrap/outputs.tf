output "state_bucket" {
  value       = aws_s3_bucket.tf_state.bucket
  description = "S3 bucket for Terraform remote state"
}

output "backend_config" {
  value       = <<-EOT
    # infra/terraform/backend.config
    bucket         = "${aws_s3_bucket.tf_state.bucket}"
    region         = "${var.aws_region}"
    use_lockfile   = true
    encrypt        = true
  EOT
  description = "Paste this into infra/terraform/backend.config after bootstrap"
}
