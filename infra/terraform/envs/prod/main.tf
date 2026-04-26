data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket       = var.state_bucket
    key          = "petrocast/shared/terraform.tfstate"
    region       = var.aws_region
    use_lockfile = true
    encrypt      = true
  }
}

locals {
  shared = data.terraform_remote_state.shared.outputs
}

module "ec2" {
  source = "../../modules/ec2-swarm-node"

  name                 = "swarm-prod"
  env                  = "prod"
  project              = var.project
  vpc_id               = local.shared.vpc_id
  subnet_id            = local.shared.public_subnet_ids[0]
  instance_type        = var.instance_type
  aws_region           = var.aws_region
  ecr_registry_id      = local.shared.ecr_registry_id
  enable_dns01_acme    = false
  artifacts_bucket_arn = local.shared.artifacts_bucket_arn

  user_data_base64 = base64encode(templatefile(
    "${path.module}/../../../scripts/bootstrap-swarm.sh",
    {
      aws_region         = var.aws_region
      ecr_registry       = local.shared.ecr_repository_url
      artifacts_bucket   = local.shared.artifacts_bucket
      traefik_acme_email = var.traefik_acme_email
      env                = "prod"
      acme_resolver      = "le"
      domain             = var.domain
      route53_zone_id    = ""
    }
  ))
}

resource "aws_route53_record" "prod" {
  zone_id = local.shared.route53_zone_id
  name    = "api.${var.domain}"
  type    = "A"
  ttl     = 60
  records = [module.ec2.public_ip]
}
