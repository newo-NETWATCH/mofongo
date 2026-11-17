output "bucket_name" {
  description = "Name of the photos bucket."
  value       = aws_s3_bucket.photos.bucket
}

output "bucket_arn" {
  description = "ARN of the photos bucket."
  value       = aws_s3_bucket.photos.arn
}
