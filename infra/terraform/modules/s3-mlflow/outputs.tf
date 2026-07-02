output "bucket" {
  value       = aws_s3_bucket.this.bucket
  description = "MLflow artifacts bucket name"
}

output "bucket_arn" {
  value       = aws_s3_bucket.this.arn
  description = "MLflow artifacts bucket ARN"
}

output "artifact_root" {
  value       = "s3://${aws_s3_bucket.this.bucket}/${var.artifact_prefix}"
  description = "PETROCAST_MLFLOW_ARTIFACT_ROOT value (MLflow --default-artifact-root)"
}

output "iam_access_key_id" {
  value       = var.create_iam_user ? aws_iam_access_key.mlflow[0].id : null
  description = "AWS_ACCESS_KEY_ID for the MLflow artifacts IAM user (null if create_iam_user=false)"
}

output "iam_secret_access_key" {
  value       = var.create_iam_user ? aws_iam_access_key.mlflow[0].secret : null
  sensitive   = true
  description = "AWS_SECRET_ACCESS_KEY for the MLflow artifacts IAM user — retrieve with `terraform output -raw`"
}
