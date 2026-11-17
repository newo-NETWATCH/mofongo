variable "name_prefix" {
  description = "Prefix for every resource name, for example mofongo-dev. The function is named <name_prefix>-matcher and its failure queue <name_prefix>-matcher-failed."
  type        = string
}

variable "package_dir" {
  description = "Staging folder that holds the matcher code (backend/matcher, plus any dependencies). The zip is written next to it as <package_dir>.zip."
  type        = string
}

variable "handler" {
  description = "Lambda handler as <module>.<function>. The module's .py file must be at the top of package_dir; plan fails with a message if it is missing."
  type        = string
  default     = "app.handler"

  validation {
    condition     = can(regex("^[A-Za-z_][A-Za-z0-9_]*\\.[A-Za-z_][A-Za-z0-9_]*$", var.handler))
    error_message = "handler must look like app.handler (a top-level module, a dot, a function)."
  }
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
  description = "Index names from the dynamodb module (same object type as its index_names output). The Lambda gets IDX_LISTED_BY_CATEGORY (items.listed_by_category) and IDX_OPEN_BY_CATEGORY (reports.open_by_category). The other two indexes are the API's and are neither passed on nor granted."
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

variable "stream_arns" {
  description = "Stream ARNs from the dynamodb module (same object type as its stream_arns output). Each event source mapping reads one, and the role may read exactly these two. Turning a stream off and on creates a new ARN and replaces the mapping (data-model 6.1)."
  type = object({
    items   = string
    reports = string
  })
}

variable "alerts_topic_arn" {
  description = "ARN of the alerts SNS topic (from the alerts_topic module). The role may publish to it and to nothing else."
  type        = string
}

variable "site_url" {
  description = "Public site origin the email links to (SITE_URL), for example https://dxxxx.cloudfront.net. The message body is <site_url>/reports/<reportId> (data-model 6.7). No trailing slash."
  type        = string

  validation {
    condition     = can(regex("^https?://[^*/]+$", var.site_url))
    error_message = "site_url must be one origin like https://example.cloudfront.net (no path, no trailing slash)."
  }
}

variable "match_threshold" {
  description = "A pair with a score at or above this is a match (MATCH_THRESHOLD, data-model 6.3). A first guess, tuned in week 6."
  type        = number
  default     = 60

  validation {
    condition     = var.match_threshold >= 1 && var.match_threshold <= 100 && floor(var.match_threshold) == var.match_threshold
    error_message = "match_threshold must be a whole number from 1 to 100 (the score is a whole number from 0 to 100)."
  }
}

variable "runtime" {
  description = "Lambda runtime."
  type        = string
  default     = "python3.13"
}

variable "architecture" {
  description = "x86_64 or arm64. Must match the platform the matcher's dependencies, if any, were built for."
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
  description = "Lambda timeout. A batch is up to 10 records and each can page through 500 candidates, so this is longer than the API's. If it is hit, the batch is retried and split (data-model 6.2); the conditional write keeps that safe."
  type        = number
  default     = 60

  validation {
    condition     = var.timeout_seconds >= 1 && var.timeout_seconds <= 900
    error_message = "timeout_seconds must be 1 to 900."
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

variable "log_level" {
  description = "Python log level for the handler."
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR"], var.log_level)
    error_message = "log_level must be DEBUG, INFO, WARNING or ERROR."
  }
}
