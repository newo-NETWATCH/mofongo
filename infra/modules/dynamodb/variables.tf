variable "name_prefix" {
  description = "Prefix for table names, for example mofongo-dev. Tables are named <prefix>-items, -reports, -matches and -users."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,30}$", var.name_prefix))
    error_message = "name_prefix must be lowercase letters, digits and hyphens, 2 to 31 characters."
  }
}

variable "deletion_protection" {
  description = "Block DeleteTable on all four tables (data-model 8.6). To tear down on purpose: set false, apply, then destroy."
  type        = bool
  default     = true
  nullable    = false
}

variable "point_in_time_recovery" {
  description = "Point-in-time recovery (35 days of history) on all four tables (data-model 8.6)."
  type        = bool
  default     = true
  nullable    = false
}

variable "tags" {
  description = "Extra tags, merged on top of the provider default_tags."
  type        = map(string)
  default     = {}
  nullable    = false
}
