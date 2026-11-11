output "user_pool_id" {
  description = "ID of the Cognito user pool."
  value       = aws_cognito_user_pool.this.id
}

output "user_pool_arn" {
  description = "ARN of the user pool, used as the REST API Cognito authorizer provider."
  value       = aws_cognito_user_pool.this.arn
}

output "app_client_id" {
  description = "ID of the public web app client (not a secret). Its ID token is the one the API accepts."
  value       = aws_cognito_user_pool_client.web.id
}

output "issuer_url" {
  description = "Token issuer (iss claim) for the user pool."
  value       = "https://cognito-idp.${data.aws_region.current.region}.amazonaws.com/${aws_cognito_user_pool.this.id}"
}

output "hosted_domain" {
  description = "Base URL of the Cognito hosted sign-in domain."
  value       = "https://${aws_cognito_user_pool_domain.this.domain}.auth.${data.aws_region.current.region}.amazoncognito.com"
}
