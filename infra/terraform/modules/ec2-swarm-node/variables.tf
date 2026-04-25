variable "name" {
  type        = string
  description = "Unique name for this node, e.g. swarm-preview-dev"
}

variable "env" {
  type        = string
  description = "Environment label: preview | staging | prod"
}

variable "project" {
  type        = string
  description = "Project name"
}

variable "vpc_id" {
  type        = string
  description = "VPC where the EC2 will be placed"
}

variable "subnet_id" {
  type        = string
  description = "Public subnet for the EC2"
}

variable "instance_type" {
  type        = string
  default     = "t3.small"
  description = "EC2 instance type"
}

variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region, used to scope ECR and CloudWatch policies"
}

variable "ecr_registry_id" {
  type        = string
  description = "AWS account ID (ECR registry) for ECR read access"
}

variable "user_data_base64" {
  type        = string
  description = "Base64-encoded cloud-init user data script"
}

variable "route53_zone_id" {
  type        = string
  default     = ""
  description = "Route 53 zone ID, required when enable_dns01_acme is true"
}

variable "enable_dns01_acme" {
  type        = bool
  default     = false
  description = "Grant Route 53 write to the instance profile for Traefik DNS-01 ACME"
}

variable "cloudwatch_log_group_arns" {
  type        = list(string)
  default     = []
  description = "CloudWatch log group ARNs the EC2 can write to (awslogs driver)"
}

variable "tags" {
  type    = map(string)
  default = {}
}
