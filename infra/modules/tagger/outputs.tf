output "instance_id" {
  description = "ID of the tagger instance. Connect with: aws ssm start-session --target <id> --region us-east-2 --profile mofongo"
  value       = aws_instance.tagger.id
}

output "security_group_id" {
  description = "ID of the tagger security group (no inbound rules)."
  value       = aws_security_group.tagger.id
}

output "role_arn" {
  description = "ARN of the tagger's instance role."
  value       = aws_iam_role.tagger.arn
}

output "log_group_name" {
  description = "CloudWatch log group that receives the bootstrap and worker logs."
  value       = aws_cloudwatch_log_group.tagger.name
}

output "schedule_names" {
  description = "Names of the weekday start and stop schedules (empty when schedule_enabled is false)."
  value       = [for s in aws_scheduler_schedule.tagger : s.name]
}
