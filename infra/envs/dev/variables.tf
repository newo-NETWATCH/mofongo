variable "region" {
  description = "AWS Region for the dev stack. The AWS project only allows its selected Region, us-east-2."
  type        = string
  default     = "us-east-2"
}

variable "aws_profile" {
  description = "AWS CLI profile Terraform signs in with."
  type        = string
  default     = "mofongo"
}

variable "alert_email" {
  description = "Email address that receives budget alerts. Set it in terraform.tfvars."
  type        = string
}

variable "monthly_budget_usd" {
  description = "Monthly spending limit in US dollars before alerts are sent."
  type        = number
  default     = 20
}

variable "cors_origin" {
  description = "The one web origin allowed to call the API and upload photos from a browser. Never a wildcard. Change it to the CloudFront URL after the web app is deployed."
  type        = string
  default     = "http://localhost:5173"

  validation {
    condition     = can(regex("^(https://[^/*]+|http://localhost:[0-9]+)$", var.cors_origin))
    error_message = "cors_origin must be https://<host> or http://localhost:<port>, with no path, no trailing slash and no wildcard."
  }
}

variable "cognito_domain_prefix" {
  description = "Prefix of the Cognito hosted sign-in domain. Must be unique in the Region and must not contain aws, amazon or cognito. Set it in terraform.tfvars."
  type        = string
}

variable "api_package_dir" {
  description = "Staging folder that scripts/build-api.ps1 fills. Null means build/api at the repo root."
  type        = string
  default     = null
}
