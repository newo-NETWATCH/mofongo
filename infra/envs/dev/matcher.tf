# Matcher Lambda, started by the Items and Reports DynamoDB streams (data-model section 6).
# Outside the VPC, like the API Lambda (ADR 0005). Needs build/matcher from scripts/build-matcher.ps1 before plan.
# It publishes to the alerts topic; the API Lambda only subscribes to it.

locals {
  # envs/dev -> repo root. scripts/build-matcher.ps1 writes the package to build/matcher.
  matcher_package_dir = abspath("${path.module}/../../../build/matcher")
}

module "matcher" {
  source = "../../modules/matcher"

  name_prefix = local.name_prefix
  package_dir = local.matcher_package_dir

  table_names = module.dynamodb.table_names
  table_arns  = module.dynamodb.table_arns
  index_names = module.dynamodb.index_names
  stream_arns = module.dynamodb.stream_arns

  alerts_topic_arn = module.alerts_topic.topic_arn

  # The email links to <site_url>/reports/<reportId>. cors_origin is the one web origin of the site,
  # so it is the same value; it becomes the CloudFront URL once the web app is deployed.
  site_url = var.cors_origin
}
