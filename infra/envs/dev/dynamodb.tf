module "dynamodb" {
  source = "../../modules/dynamodb"

  name_prefix = local.name_prefix
}
