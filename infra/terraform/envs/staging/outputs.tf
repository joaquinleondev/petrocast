output "instance_id" {
  value       = module.ec2.instance_id
  description = "EC2 instance ID — set as EC2_INSTANCE_ID in GitHub Environment 'staging'"
}

output "public_ip" {
  value       = module.ec2.public_ip
  description = "Public IP of the staging swarm node"
}
