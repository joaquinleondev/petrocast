variable "project" {
  type        = string
  description = "Project name"
}

variable "tags" {
  type    = map(string)
  default = {}
}
