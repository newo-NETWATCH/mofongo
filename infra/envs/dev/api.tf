module "api" {
  source = "../../modules/api"

  name_prefix = local.name_prefix
  region      = var.region
  account_id  = local.account_id

  lambda_invoke_arn     = module.api_lambda.invoke_arn
  lambda_function_name  = module.api_lambda.function_name
  cognito_user_pool_arn = module.cognito.user_pool_arn

  cors_origin = var.cors_origin
}
