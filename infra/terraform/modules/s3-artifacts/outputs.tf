output "artifacts_bucket" {
  value       = aws_s3_bucket.this["artifacts"].bucket
  description = "Pipeline artifacts bucket name"
}

output "artifacts_bucket_arn" {
  value       = aws_s3_bucket.this["artifacts"].arn
  description = "Pipeline artifacts bucket ARN"
}

output "reports_bucket" {
  value       = aws_s3_bucket.this["reports"].bucket
  description = "Test reports bucket name"
}

output "reports_bucket_arn" {
  value       = aws_s3_bucket.this["reports"].arn
  description = "Test reports bucket ARN"
}
