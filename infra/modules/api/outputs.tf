output "rest_api_id" {
  description = "ID of the REST API."
  value       = aws_api_gateway_rest_api.this.id
}

output "stage_arn" {
  description = "ARN of the stage. Use it to associate a regional WAF web ACL."
  value       = aws_api_gateway_stage.this.arn
}

output "stage_name" {
  description = "Name of the stage."
  value       = aws_api_gateway_stage.this.stage_name
}

output "execution_arn" {
  description = "Execution ARN of the API, for IAM or Lambda permissions."
  value       = aws_api_gateway_rest_api.this.execution_arn
}

output "invoke_url" {
  description = "Base URL of the stage, for example https://<id>.execute-api.us-east-2.amazonaws.com/dev. Routes are added after it."
  value       = aws_api_gateway_stage.this.invoke_url
}

output "authorizer_id" {
  description = "ID of the Cognito User Pools authorizer."
  value       = aws_api_gateway_authorizer.cognito.id
}

output "access_log_group_name" {
  description = "CloudWatch log group that receives the access log."
  value       = aws_cloudwatch_log_group.access.name
}
