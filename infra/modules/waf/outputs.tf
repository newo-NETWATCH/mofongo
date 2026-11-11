output "web_acl_arn" {
  description = "ARN of the regional web ACL."
  value       = aws_wafv2_web_acl.api.arn
}
