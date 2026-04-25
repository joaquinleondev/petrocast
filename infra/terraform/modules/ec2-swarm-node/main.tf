data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# ── Security Group ─────────────────────────────────────────────────────────────
resource "aws_security_group" "this" {
  name        = "${var.project}-${var.name}-sg"
  description = "Swarm node SG for ${var.name}"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP (ACME HTTP-01 challenge)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # SSH intentionally omitted — access via SSM Run Command only

  egress {
    description = "All outbound (ECR, SSM, internet)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge({ Name = "${var.project}-${var.name}-sg" }, var.tags)
}

# ── IAM ────────────────────────────────────────────────────────────────────────
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${var.project}-${var.name}-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "ecr_read" {
  statement {
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
      "ecr:DescribeImages",
    ]
    resources = [
      "arn:aws:ecr:${var.aws_region}:${var.ecr_registry_id}:repository/${var.project}/*",
    ]
  }
}

resource "aws_iam_role_policy" "ecr_read" {
  name   = "ecr-read"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.ecr_read.json
}

data "aws_iam_policy_document" "cloudwatch_logs" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogStreams",
    ]
    resources = length(var.cloudwatch_log_group_arns) > 0 ? [
      for arn in var.cloudwatch_log_group_arns : "${arn}:*"
    ] : ["arn:aws:logs:${var.aws_region}:*:log-group:/${var.project}/${var.env}/*:*"]
  }
}

resource "aws_iam_role_policy" "cloudwatch_logs" {
  name   = "cloudwatch-logs-write"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.cloudwatch_logs.json
}

# Optional Route 53 write for Traefik ACME DNS-01 (preview only)
data "aws_iam_policy_document" "route53_acme" {
  count = var.enable_dns01_acme ? 1 : 0

  statement {
    effect = "Allow"
    actions = [
      "route53:GetChange",
      "route53:ListHostedZonesByName",
    ]
    resources = ["*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["route53:ChangeResourceRecordSets"]
    resources = ["arn:aws:route53:::hostedzone/${var.route53_zone_id}"]
  }
}

resource "aws_iam_role_policy" "route53_acme" {
  count  = var.enable_dns01_acme ? 1 : 0
  name   = "route53-acme-dns01"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.route53_acme[0].json
}

resource "aws_iam_instance_profile" "this" {
  name = "${var.project}-${var.name}-profile"
  role = aws_iam_role.this.name
  tags = var.tags
}

# ── EC2 Instance ───────────────────────────────────────────────────────────────
resource "aws_instance" "this" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  subnet_id              = var.subnet_id
  iam_instance_profile   = aws_iam_instance_profile.this.name
  vpc_security_group_ids = [aws_security_group.this.id]
  user_data_base64       = var.user_data_base64

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 20
    delete_on_termination = true
    encrypted             = true
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 2
  }

  tags = merge(
    {
      Name    = "${var.project}-${var.name}"
      Env     = var.env
      Project = var.project
    },
    var.tags,
  )

  lifecycle {
    ignore_changes = [user_data_base64, ami]
  }
}

resource "aws_eip" "this" {
  domain = "vpc"
  tags   = merge({ Name = "${var.project}-${var.name}-eip" }, var.tags)
}

resource "aws_eip_association" "this" {
  instance_id   = aws_instance.this.id
  allocation_id = aws_eip.this.id
}
