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

  name                 = "swarm-staging"
  env                  = "staging"
  project              = var.project
  vpc_id               = local.shared.vpc_id
  subnet_id            = local.shared.public_subnet_ids[1]
  instance_type        = var.instance_type
  aws_region           = var.aws_region
  ecr_registry_id      = local.shared.ecr_registry_id
  enable_dns01_acme    = false
  artifacts_bucket_arn = local.shared.artifacts_bucket_arn

  # Phase-2 data stack: bigger root for images, a persistent data volume, and
  # read access to the data-stack secrets in SSM Parameter Store.
  root_volume_size   = 50
  data_volume_size   = 40
  data_snapshot_id   = var.data_snapshot_id
  enable_ssm_secrets = true
  ssm_secrets_path   = "/petrocast/staging/data/*"

  user_data_base64 = base64encode(templatefile(
    "${path.module}/../../../scripts/bootstrap-swarm.sh",
    {
      aws_region         = var.aws_region
      ecr_registry       = local.shared.ecr_repository_url
      artifacts_bucket   = local.shared.artifacts_bucket
      traefik_acme_email = var.traefik_acme_email
      env                = "staging"
      acme_resolver      = "le"
      domain             = var.domain
      route53_zone_id    = ""
      data_stack_enabled = "true"
    }
  ))
}

resource "aws_route53_record" "staging" {
  zone_id = local.shared.route53_zone_id
  name    = "staging.${var.domain}"
  type    = "A"
  ttl     = 60
  records = [module.ec2.public_ip]
}

# Subdomains for the data-stack UIs (Traefik routes by host, basic-auth + TLS).
resource "aws_route53_record" "data_uis" {
  for_each = toset(["api", "bi", "dagster", "datahub"])
  zone_id  = local.shared.route53_zone_id
  name     = "${each.value}.staging.${var.domain}"
  type     = "A"
  ttl      = 60
  records  = [module.ec2.public_ip]
}
