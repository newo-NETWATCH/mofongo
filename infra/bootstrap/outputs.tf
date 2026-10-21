output "state_bucket_name" {
  description = "Put this name in bootstrap/backend.tf and envs/dev/backend.tf."
  value       = aws_s3_bucket.state.bucket
}
