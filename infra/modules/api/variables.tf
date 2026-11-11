variable "name_prefix" {
  description = "Prefix for every resource name, for example mofongo-dev. The API is named <name_prefix>-api."
  type        = string
}

variable "region" {
  description = "Region of the API. Always us-east-2 in this project."
  type        = string
}

variable "account_id" {
  description = "AWS account ID. Used to scope the API Gateway logging role to this account."
  type        = string
}

variable "lambda_invoke_arn" {
  description = "invoke_arn of the API Lambda (the arn:aws:apigateway:...:lambda:path/... form). Comes from the api_lambda module."
  type        = string
}

variable "lambda_function_name" {
  description = "Name of the API Lambda, for the invoke permission. Comes from the api_lambda module."
  type        = string
}

variable "cognito_user_pool_arn" {
  description = "ARN of the Cognito user pool that signs the ID tokens. Comes from the cognito module."
  type        = string
}

variable "cors_origin" {
  description = "The one web origin allowed to call the API from a browser. Never a wildcard."
  type        = string
  default     = "http://localhost:5173"

  validation {
    condition     = !strcontains(var.cors_origin, "*")
    error_message = "cors_origin must be one exact origin. A wildcard is not allowed."
  }

  validation {
    condition     = can(regex("^(https://[^/]+|http://localhost:[0-9]+)$", var.cors_origin))
    error_message = "cors_origin must be https://<host> or http://localhost:<port>, with no path and no trailing slash."
  }
}

variable "stage_name" {
  description = "Name of the single stage. It is part of the invoke URL."
  type        = string
  default     = "dev"
}

variable "throttle_rate" {
  description = "Stage default: steady requests per second, shared by all callers."
  type        = number
  default     = 20

  validation {
    condition     = var.throttle_rate > 0
    error_message = "throttle_rate must be greater than 0."
  }
}

variable "throttle_burst" {
  description = "Stage default: burst size."
  type        = number
  default     = 10

  validation {
    condition     = var.throttle_burst > 0
    error_message = "throttle_burst must be greater than 0."
  }
}

variable "write_throttle_rate" {
  description = "Requests per second for POST /items and POST /me/alerts (photo upload form, SNS email). Shared by all callers."
  type        = number
  default     = 1

  validation {
    condition     = var.write_throttle_rate > 0
    error_message = "write_throttle_rate must be greater than 0."
  }
}

variable "write_throttle_burst" {
  description = "Burst size for POST /items and POST /me/alerts."
  type        = number
  default     = 5

  validation {
    condition     = var.write_throttle_burst > 0
    error_message = "write_throttle_burst must be greater than 0."
  }
}

variable "integration_timeout_ms" {
  description = "How long API Gateway waits for the Lambda. Keep it at or above the Lambda timeout."
  type        = number
  default     = 10000

  validation {
    condition     = var.integration_timeout_ms >= 50 && var.integration_timeout_ms <= 29000
    error_message = "integration_timeout_ms must be between 50 and 29000."
  }
}

variable "log_retention_days" {
  description = "Days to keep the access log."
  type        = number
  default     = 30
}

variable "manage_account_cloudwatch_role" {
  description = "Set the API Gateway account-level CloudWatch Logs role for this Region. It is one setting per account and Region, and access logging fails without it. Set false if another stack already owns it."
  type        = bool
  default     = true
}

variable "schema_dir" {
  description = "Folder that holds create-item.json and create-report.json. Null means api/schemas/requests in this repo."
  type        = string
  default     = null
}
