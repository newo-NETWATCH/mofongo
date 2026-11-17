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

output "matcher_function_name" {
  description = "Name of the matcher Lambda (started by the Items and Reports streams)."
  value       = module.matcher.function_name
}

output "matcher_failed_queue_name" {
  description = "Failure queue of the matcher's event source mappings. Alarm on it being non-empty."
  value       = module.matcher.failed_queue_name
}

output "tagger_instance_id" {
  description = "Tagger EC2 instance ID. Connect with: aws ssm start-session --target <id> --region us-east-2 --profile mofongo"
  value       = module.tagger.instance_id
}

output "tagger_log_group_name" {
  description = "CloudWatch log group with the tagger's bootstrap and worker logs."
  value       = module.tagger.log_group_name
}

output "photo_queue_url" {
  description = "URL of the photo queue the tagger polls."
  value       = module.photo_queue.queue_url
}

output "photo_dlq_url" {
  description = "URL of the photo dead-letter queue. Photos that failed tagging end up here."
  value       = module.photo_queue.dlq_url
}

output "vpc_id" {
  description = "ID of the VPC."
  value       = module.vpc.vpc_id
}

output "nat_public_ip" {
  description = "Elastic IP of the NAT gateway: the source address of all tagger outbound traffic."
  value       = module.vpc.nat_public_ip
}
