variable "project" {
  type        = string
  description = "Project name used for resource naming"
}

variable "cidr" {
  type        = string
  default     = "10.0.0.0/16"
  description = "VPC CIDR block"
}

variable "availability_zones" {
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
  description = "AZs for public subnets"
}

variable "tags" {
  type    = map(string)
  default = {}
}
