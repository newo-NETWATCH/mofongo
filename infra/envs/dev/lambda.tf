# API Lambda. Outside the VPC (ADR 0005). Needs build/api from scripts/build-api.ps1 before plan.
module "api_lambda" {
  source = "../../modules/api_lambda"

  name_prefix = local.name_prefix
  package_dir = local.api_package_dir

  table_names = module.dynamodb.table_names
  table_arns  = module.dynamodb.table_arns
  index_names = module.dynamodb.index_names

  photos_bucket_name = module.photos_bucket.bucket_name
  photos_bucket_arn  = module.photos_bucket.bucket_arn
  alerts_topic_arn   = module.alerts_topic.topic_arn

  cognito_user_pool_id  = module.cognito.user_pool_id
  cognito_app_client_id = module.cognito.app_client_id

  cors_origin = var.cors_origin
}
