output "function_name" {
  description = "Name of the matcher Lambda."
  value       = aws_lambda_function.matcher.function_name
}

output "function_arn" {
  description = "ARN of the matcher Lambda."
  value       = aws_lambda_function.matcher.arn
}

output "role_arn" {
  description = "ARN of the Lambda's execution role."
  value       = aws_iam_role.matcher.arn
}

output "role_name" {
  description = "Name of the Lambda's execution role."
  value       = aws_iam_role.matcher.name
}

output "log_group_name" {
  description = "CloudWatch log group of the Lambda."
  value       = aws_cloudwatch_log_group.matcher.name
}

output "failed_queue_name" {
  description = "Name of the failure queue (<prefix>-matcher-failed). Alarm on ApproximateNumberOfMessagesVisible above 0."
  value       = aws_sqs_queue.failed.name
}

output "failed_queue_arn" {
  description = "ARN of the failure queue."
  value       = aws_sqs_queue.failed.arn
}

output "event_source_mapping_ids" {
  description = "UUIDs of the two event source mappings, by stream."
  value = {
    items   = aws_lambda_event_source_mapping.items.uuid
    reports = aws_lambda_event_source_mapping.reports.uuid
  }
}

output "source_code_hash" {
  description = "Hash of the deployed zip. Useful when checking for deploy drift."
  value       = data.archive_file.matcher.output_base64sha256
}
