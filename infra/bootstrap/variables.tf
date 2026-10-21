variable "region" {
  description = "AWS Region for the state bucket. The AWS project only allows its selected Region, us-east-2."
  type        = string
  default     = "us-east-2"
}

variable "aws_profile" {
  description = "AWS CLI profile Terraform signs in with."
  type        = string
  default     = "mofongo"
}
