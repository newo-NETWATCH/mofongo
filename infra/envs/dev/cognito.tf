module "cognito" {
  source = "../../modules/cognito"

  name_prefix   = local.name_prefix
  domain_prefix = var.cognito_domain_prefix
  callback_urls = ["${var.cors_origin}/"]
  logout_urls   = ["${var.cors_origin}/"]
}
