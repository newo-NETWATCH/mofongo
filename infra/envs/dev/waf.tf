# Regional web ACL on the REST API stage (us-east-2; not CloudFront).
module "waf" {
  source = "../../modules/waf"

  resource_arn = module.api.stage_arn
}
