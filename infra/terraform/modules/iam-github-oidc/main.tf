data "aws_caller_identity" "current" {}

locals {
  oidc_url  = "https://token.actions.githubusercontent.com"
  oidc_host = "token.actions.githubusercontent.com"
  # AWS no longer validates thumbprints for GitHub's OIDC endpoint but the field is required.
  thumbprint = "6938fd4d98bab03faadb97b34396831e3780aea1"
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = local.oidc_url
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [local.thumbprint]
  tags            = var.tags
}

# ── ci-role: assumed by any GHA run in the repo (build, lint, test, scan) ────
data "aws_iam_policy_document" "ci_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "${local.oidc_host}:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

data "aws_iam_policy_document" "ci_permissions" {
  # ECR auth token (registry-level, no resource restriction)
  statement {
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  # ECR push + pull for the specific repo
  statement {
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
      "ecr:ListImages",
    ]
    resources = [var.ecr_repository_arn]
  }

  # S3 artifacts and reports
  statement {
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      var.artifacts_bucket_arn,
      "${var.artifacts_bucket_arn}/*",
      var.reports_bucket_arn,
      "${var.reports_bucket_arn}/*",
    ]
  }

  # Terraform remote state — read for tf-plan
  statement {
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      var.tf_state_bucket_arn,
      "${var.tf_state_bucket_arn}/*",
    ]
  }

  # Terraform DynamoDB lock — acquire/release during plan
  statement {
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
    ]
    resources = [var.tf_lock_table_arn]
  }
}

resource "aws_iam_role" "ci" {
  name               = "github-actions-ci"
  assume_role_policy = data.aws_iam_policy_document.ci_trust.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "ci" {
  name   = "github-actions-ci-policy"
  role   = aws_iam_role.ci.id
  policy = data.aws_iam_policy_document.ci_permissions.json
}

# Terraform plan needs read on every resource it manages — attach managed ReadOnlyAccess.
resource "aws_iam_role_policy_attachment" "ci_readonly" {
  role       = aws_iam_role.ci.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# ── deploy-role: assumed only from main, v* tags, or explicit environments ────
data "aws_iam_policy_document" "deploy_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "${local.oidc_host}:sub"
      values = [
        "repo:${var.github_repo}:ref:refs/heads/main",
        "repo:${var.github_repo}:ref:refs/tags/v*",
        "repo:${var.github_repo}:environment:preview",
        "repo:${var.github_repo}:environment:staging",
        "repo:${var.github_repo}:environment:production",
        # pull_request events need to deploy previews
        "repo:${var.github_repo}:pull_request",
      ]
    }
  }
}

data "aws_iam_policy_document" "deploy_permissions" {
  # SSM Run Command — scoped to EC2 instances tagged Project=petrocast
  statement {
    effect  = "Allow"
    actions = ["ssm:SendCommand"]
    resources = [
      "arn:aws:ec2:*:${data.aws_caller_identity.current.account_id}:instance/*",
    ]
    condition {
      test     = "StringLike"
      variable = "ssm:resourceTag/Project"
      values   = ["petrocast"]
    }
  }

  statement {
    effect    = "Allow"
    actions   = ["ssm:SendCommand"]
    resources = ["arn:aws:ssm:*:*:document/AWS-RunShellScript"]
  }

  statement {
    effect = "Allow"
    actions = [
      "ssm:GetCommandInvocation",
      "ssm:ListCommandInvocations",
    ]
    resources = ["*"]
  }

  # ECR re-tagging for promote-to-prod step
  statement {
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
    ]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
      "ecr:PutImage",
      "ecr:DescribeImages",
    ]
    resources = [var.ecr_repository_arn]
  }
}

resource "aws_iam_role" "deploy" {
  name               = "github-actions-deploy"
  assume_role_policy = data.aws_iam_policy_document.deploy_trust.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "deploy" {
  name   = "github-actions-deploy-policy"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy_permissions.json
}
