output "queue_url" {
  description = "URL of the photo queue (<prefix>-photos). The tagger worker polls this."
  value       = aws_sqs_queue.photos.url
}

output "queue_arn" {
  description = "ARN of the photo queue. Target of the S3 bucket notification and of the tagger role's receive permissions."
  value       = aws_sqs_queue.photos.arn
}

output "dlq_url" {
  description = "URL of the dead-letter queue (<prefix>-photos-dlq)."
  value       = aws_sqs_queue.dlq.url
}

output "dlq_arn" {
  description = "ARN of the dead-letter queue."
  value       = aws_sqs_queue.dlq.arn
}
