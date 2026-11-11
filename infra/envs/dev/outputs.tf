output "api_invoke_url" {
  description = "Base URL of the API stage. Routes are added after it."
  value       = module.api.invoke_url
}

output "cognito_user_pool_id" {
  description = "Cognito user pool ID."
  value       = module.cognito.user_pool_id
}

output "cognito_app_client_id" {
  description = "Public web app client ID (not a secret)."
  value       = module.cognito.app_client_id
}

output "cognito_hosted_domain" {
  description = "Base URL of the Cognito hosted sign-in domain."
  value       = module.cognito.hosted_domain
}

output "table_names" {
  description = "DynamoDB table names by role."
  value       = module.dynamodb.table_names
}

output "photos_bucket_name" {
  description = "Photos bucket name."
  value       = module.photos_bucket.bucket_name
}

output "alerts_topic_arn" {
  description = "SNS alerts topic ARN."
  value       = module.alerts_topic.topic_arn
}

output "web_acl_arn" {
  description = "Regional WAF web ACL ARN."
  value       = module.waf.web_acl_arn
}
