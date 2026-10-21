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
