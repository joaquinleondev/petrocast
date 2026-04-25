locals {
  envs = ["preview", "staging", "prod"]
  log_types = ["app", "traefik", "deploy"]

  log_groups = {
    for pair in setproduct(local.envs, local.log_types) :
    "${pair[0]}-${pair[1]}" => {
      env           = pair[0]
      type          = pair[1]
      name          = "/${var.project}/${pair[0]}/${pair[1]}"
      retention_days = pair[0] == "preview" ? 14 : 30
    }
  }
}

resource "aws_cloudwatch_log_group" "this" {
  for_each          = local.log_groups
  name              = each.value.name
  retention_in_days = each.value.retention_days
  tags              = merge({ Env = each.value.env, LogType = each.value.type }, var.tags)
}
