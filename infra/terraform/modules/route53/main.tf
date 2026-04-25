# Creates the hosted zone only.
# DNS A-records are created by each environment root after EC2 EIPs are known.
resource "aws_route53_zone" "this" {
  name = var.domain
  tags = var.tags
}
