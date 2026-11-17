variable "name_prefix" {
  description = "Prefix for resource names, for example mofongo-dev."
  type        = string
}

variable "domain_prefix" {
  description = "Prefix for the Cognito hosted sign-in domain (<prefix>.auth.us-east-2.amazoncognito.com). Must be unique in the Region and cannot contain aws, amazon or cognito. Set it in the git-ignored terraform.tfvars."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", var.domain_prefix)) && !can(regex("aws|amazon|cognito", var.domain_prefix))
    error_message = "domain_prefix must be 1-63 characters: lowercase letters, digits and hyphens, not starting or ending with a hyphen, and not containing aws, amazon or cognito."
  }
}

variable "callback_urls" {
  description = "Exact URLs Cognito may redirect to after sign-in, scheme and path included. A mismatch gives redirect_mismatch."
  type        = list(string)
  default     = ["http://localhost:5173/"]

  validation {
    condition     = length(var.callback_urls) > 0 && alltrue([for u in var.callback_urls : !can(regex("\\*", u)) && (startswith(u, "https://") || startswith(u, "http://localhost:"))])
    error_message = "callback_urls must not be empty or contain a wildcard, and each must start with https:// or http://localhost:."
  }
}

variable "logout_urls" {
  description = "Exact URLs Cognito may redirect to after sign-out."
  type        = list(string)
  default     = ["http://localhost:5173/"]

  validation {
    condition     = length(var.logout_urls) > 0 && alltrue([for u in var.logout_urls : !can(regex("\\*", u)) && (startswith(u, "https://") || startswith(u, "http://localhost:"))])
    error_message = "logout_urls must not be empty or contain a wildcard, and each must start with https:// or http://localhost:."
  }
}

variable "user_pool_tier" {
  description = "Cognito feature plan: LITE or ESSENTIALS. Threat protection needs PLUS (paid), which this dev stack does not use."
  type        = string
  default     = "ESSENTIALS"

  validation {
    condition     = contains(["LITE", "ESSENTIALS"], var.user_pool_tier)
    error_message = "user_pool_tier must be LITE or ESSENTIALS."
  }
}

variable "deletion_protection" {
  description = "ACTIVE blocks deleting the user pool (users cannot be recreated). Set INACTIVE, apply, then destroy to tear down."
  type        = string
  default     = "ACTIVE"

  validation {
    condition     = contains(["ACTIVE", "INACTIVE"], var.deletion_protection)
    error_message = "deletion_protection must be ACTIVE or INACTIVE."
  }
}

variable "token_minutes" {
  description = "Lifetime of ID and access tokens, in minutes."
  type        = number
  default     = 60

  validation {
    condition     = var.token_minutes >= 5 && var.token_minutes <= 1440
    error_message = "token_minutes must be between 5 and 1440."
  }
}

variable "refresh_token_days" {
  description = "Lifetime of the refresh token, in days. Keep it short because the web app stores it."
  type        = number
  default     = 30

  validation {
    condition     = var.refresh_token_days >= 1 && var.refresh_token_days <= 3650
    error_message = "refresh_token_days must be between 1 and 3650."
  }
}
