variable "account_id" {
  description = "AWS account ID of the project. Makes the bucket name unique worldwide."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be a 12-digit AWS account ID."
  }
}

variable "cors_origin" {
  description = "Browser origin allowed to upload photos with a presigned PUT."
  type        = string
  default     = "http://localhost:5173"
}
