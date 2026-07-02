# MLflow artifact store (ADR-0032, F3-08).
#
# Deliberately a SEPARATE module from `s3-artifacts`: that one force-expires
# every object after `lifecycle_days` (90d), which would silently delete the
# champion model. Here the current object versions (the live artifacts) NEVER
# expire — only stale noncurrent versions are reaped.
#
# Access model: MLflow clients upload artifacts DIRECTLY to S3 (the server does
# not proxy them), so team members running MLflow from their laptops need static
# credentials — laptops can't use the GitHub OIDC role or an EC2 instance
# profile. This module optionally mints a dedicated, bucket-scoped IAM user +
# access key for that. The secret lands in Terraform state (encrypted S3
# backend) and is exposed as a sensitive output; share it via the team's secure
# channel, never via git.

locals {
  bucket_name = "${var.project}-ml-artifacts"
}

resource "aws_s3_bucket" "this" {
  bucket        = local.bucket_name
  force_destroy = var.force_destroy
  tags          = merge({ Name = local.bucket_name }, var.tags)
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# NOTE: no `expiration {}` block on purpose — model artifacts must persist.
# We only clean up noncurrent versions to keep storage bounded.
resource "aws_s3_bucket_lifecycle_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"
    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_expiration_days
    }
  }
}

# ── Dedicated IAM user for laptop-based MLflow clients ────────────────────────
resource "aws_iam_user" "mlflow" {
  count = var.create_iam_user ? 1 : 0
  name  = "${var.project}-mlflow-artifacts"
  tags  = var.tags
}

data "aws_iam_policy_document" "mlflow_s3" {
  statement {
    sid       = "ListBucket"
    effect    = "Allow"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.this.arn]
  }

  statement {
    sid    = "ObjectRW"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.this.arn}/*"]
  }
}

resource "aws_iam_user_policy" "mlflow" {
  count  = var.create_iam_user ? 1 : 0
  name   = "${var.project}-mlflow-artifacts-s3"
  user   = aws_iam_user.mlflow[0].name
  policy = data.aws_iam_policy_document.mlflow_s3.json
}

resource "aws_iam_access_key" "mlflow" {
  count = var.create_iam_user ? 1 : 0
  user  = aws_iam_user.mlflow[0].name
}
