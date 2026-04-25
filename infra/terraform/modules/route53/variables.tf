variable "domain" {
  type        = string
  description = "Root domain, e.g. petrocast.shop"
}

variable "tags" {
  type    = map(string)
  default = {}
}
