variable "name_prefix" {
  description = "Prefix for every resource name, for example mofongo-dev. The function is named <name_prefix>-api."
  type        = string
}

variable "package_dir" {
  description = "Staging folder that scripts/build-api.ps1 fills: the backend/api code, its Linux-built dependencies and schemas/requests + schemas/shared copied from api/schemas. The zip is written next to it as <package_dir>.zip."
  type        = string
}

variable "table_names" {
  description = "Table names from the dynamodb module (same object type as its table_names output)."
  type = object({
    items   = string
    reports = string
    matches = string
    users   = string
  })
}

variable "table_arns" {
  description = "Table ARNs from the dynamodb module (same object type as its table_arns output)."
  type = object({
    items   = string
    reports = string
    matches = string
    users   = string
  })
}

variable "index_names" {
  description = "Index names from the dynamodb module. The Lambda gets IDX_LISTED_BY_DATE (items.listed_by_date), IDX_LISTED_BY_CATEGORY (items.listed_by_category) and IDX_BY_OWNER (reports.by_owner). reports.open_by_category belongs to the matcher: it is not passed on and not granted."
  type = object({
    items = object({
      listed_by_date     = string
      listed_by_category = string
    })
    reports = object({
      by_owner         = string
      open_by_category = string
    })
  })
}

variable "photos_bucket_name" {
  description = "Name of the photos bucket (from the photos_bucket module)."
  type        = string
}

variable "photos_bucket_arn" {
  description = "ARN of the photos bucket. The role may presign PutObject and GetObject on photos/* only."
  type        = string
}

variable "alerts_topic_arn" {
  description = "ARN of the alerts SNS topic (from the alerts_topic module). The role may subscribe to it and read subscription state, not publish."
  type        = string
}

variable "cognito_user_pool_id" {
  description = "Cognito user pool ID. The handler checks the token's iss against it."
  type        = string
}

variable "cognito_app_client_id" {
  description = "Cognito app client ID. The handler checks the token's aud against it."
  type        = string
}

variable "cors_origin" {
  description = "The one site origin the Lambda puts in Access-Control-Allow-Origin on its answers. A REST API does not add it for you. Never *."
  type        = string
  default     = "http://localhost:5173"

  validation {
    condition     = can(regex("^https?://[^*/]+$", var.cors_origin))
    error_message = "cors_origin must be one origin like https://example.cloudfront.net (no wildcard, no path)."
  }
}

variable "runtime" {
  description = "Lambda runtime."
  type        = string
  default     = "python3.13"
}

variable "architecture" {
  description = "x86_64 or arm64. Must match the --platform that scripts/build-api.ps1 passes to pip."
  type        = string
  default     = "x86_64"

  validation {
    condition     = contains(["x86_64", "arm64"], var.architecture)
    error_message = "architecture must be x86_64 or arm64."
  }
}

variable "memory_mb" {
  description = "Lambda memory in MB."
  type        = number
  default     = 256
}

variable "timeout_seconds" {
  description = "Lambda timeout. Keep it at or below the API Gateway integration timeout (10 s in the api module's default)."
  type        = number
  default     = 10

  validation {
    condition     = var.timeout_seconds >= 1 && var.timeout_seconds <= 29
    error_message = "timeout_seconds must be 1 to 29 (REST API integrations time out at 29 s by default)."
  }
}

variable "log_retention_days" {
  description = "How long the Lambda's CloudWatch log group keeps logs."
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365], var.log_retention_days)
    error_message = "log_retention_days must be a value CloudWatch Logs accepts, for example 7, 14, 30 or 90."
  }
}

variable "presign_ttl_seconds" {
  description = "Lifetime of a photo view link. api/openapi.yaml says 15 minutes."
  type        = number
  default     = 900
}

variable "photo_max_bytes" {
  description = "Largest photo the presigned upload form accepts (content-length-range). 10 MB."
  type        = number
  default     = 10485760
}

variable "log_level" {
  description = "Python log level for the handler."
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR"], var.log_level)
    error_message = "log_level must be DEBUG, INFO, WARNING or ERROR."
  }
}
