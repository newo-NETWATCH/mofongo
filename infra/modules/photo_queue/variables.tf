variable "name_prefix" {
  description = "Prefix for every resource name, for example mofongo-dev. The queue is named <name_prefix>-photos and its dead-letter queue <name_prefix>-photos-dlq."
  type        = string
}

variable "photos_bucket_arn" {
  description = "ARN of the photos bucket (from the photos_bucket module). The queue policy lets S3 send messages only when the event comes from this bucket."
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:s3:::[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.photos_bucket_arn))
    error_message = "photos_bucket_arn must be an S3 bucket ARN like arn:aws:s3:::my-bucket (no /* suffix)."
  }
}

variable "account_id" {
  description = "AWS account ID of the project. Used as aws:SourceAccount in the queue policy, because a bucket ARN does not contain the account ID (confused deputy guard, docs/plan.md Part 3)."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be 12 digits."
  }
}

variable "alarm_actions" {
  description = "ARNs to notify when the dead-letter queue alarm goes to ALARM and when it clears, for example the alerts SNS topic. Empty means the alarm only shows in the console."
  type        = list(string)
  default     = []
}

variable "visibility_timeout_seconds" {
  description = "How long a received message is hidden from other receives. Must be longer than one tagging run (download the photo, score it with CLIP, write the item), or the same photo is handed out twice. docs/decisions/0004."
  type        = number
  default     = 300

  validation {
    condition     = var.visibility_timeout_seconds >= 60 && var.visibility_timeout_seconds <= 43200
    error_message = "visibility_timeout_seconds must be 60 to 43200 (12 hours, the SQS maximum)."
  }
}

variable "max_receive_count" {
  description = "How many times a message is received before SQS moves it to the dead-letter queue. A photo that fails this many times stops blocking the others. ADR 0004 says 'the set number of tries' without a number; 5 is the first guess and also rides out a worker that restarts."
  type        = number
  default     = 5

  validation {
    condition     = var.max_receive_count >= 1 && var.max_receive_count <= 1000 && floor(var.max_receive_count) == var.max_receive_count
    error_message = "max_receive_count must be a whole number from 1 to 1000."
  }
}
