variable "name" {
  description = "Name of the web ACL."
  type        = string
  default     = "mofongo-dev-api"
}

variable "resource_arn" {
  description = "ARN of the API Gateway REST API stage the web ACL protects (the api module's stage_arn)."
  type        = string
}

variable "rate_limit" {
  description = "Maximum requests from one IP address per 5 minutes before WAF blocks it."
  type        = number
  default     = 2000

  validation {
    condition     = var.rate_limit >= 10
    error_message = "WAF rate-based rules need a limit of at least 10."
  }
}
