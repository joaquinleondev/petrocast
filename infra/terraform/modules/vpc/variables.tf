variable "project" {
  type        = string
  description = "Project name used for resource naming"
}

variable "cidr" {
  type        = string
  default     = "10.0.0.0/16"
  description = "VPC CIDR block"
}

variable "public_subnet_count" {
  type        = number
  default     = 2
  description = "Number of public subnets to create across the current region's available AZs"

  validation {
    condition     = var.public_subnet_count >= 2
    error_message = "public_subnet_count must be at least 2."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
