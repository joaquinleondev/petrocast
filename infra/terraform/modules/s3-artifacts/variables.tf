variable "project" {
  type        = string
  description = "Project name used for bucket naming"
}

variable "lifecycle_days" {
  type        = number
  default     = 90
  description = "Days after which pipeline artifacts expire"
}

variable "tags" {
  type    = map(string)
  default = {}
}
