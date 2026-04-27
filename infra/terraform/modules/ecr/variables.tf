variable "name" {
  type        = string
  description = "ECR repository name, e.g. petrocast/mock-api"
}

variable "tags" {
  type    = map(string)
  default = {}
}
