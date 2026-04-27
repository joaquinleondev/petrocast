output "zone_id" {
  value       = aws_route53_zone.this.zone_id
  description = "Route 53 hosted zone ID"
}

output "nameservers" {
  value       = aws_route53_zone.this.name_servers
  description = "NS records to configure at the domain registrar"
}
