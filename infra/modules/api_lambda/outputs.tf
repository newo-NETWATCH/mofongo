output "function_name" {
  description = "Name of the API Lambda. The api module needs it for the invoke permission."
  value       = aws_lambda_function.api.function_name
}

output "function_arn" {
  description = "ARN of the API Lambda."
  value       = aws_lambda_function.api.arn
}

output "invoke_arn" {
  description = "Invoke ARN for the API Gateway AWS_PROXY integration."
  value       = aws_lambda_function.api.invoke_arn
}

output "role_arn" {
  description = "ARN of the Lambda's execution role."
  value       = aws_iam_role.api.arn
}

output "role_name" {
  description = "Name of the Lambda's execution role."
  value       = aws_iam_role.api.name
}

output "log_group_name" {
  description = "CloudWatch log group of the Lambda."
  value       = aws_cloudwatch_log_group.api.name
}

output "source_code_hash" {
  description = "Hash of the deployed zip. Useful when checking for deploy drift."
  value       = data.archive_file.api.output_base64sha256
}
