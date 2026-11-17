variable "name_prefix" {
  description = "Prefix for every resource name, for example mofongo-dev. Resources are named <name_prefix>-tagger-*."
  type        = string
}

variable "vpc_id" {
  description = "VPC the tagger security group is created in (the custom VPC of ADR 0005)."
  type        = string
}

variable "private_subnet_id" {
  description = "PRIVATE subnet the tagger runs in. It gets no public IP. In option A its route table sends 0.0.0.0/0 to the NAT gateway and holds the S3 and DynamoDB gateway endpoints."
  type        = string
}

variable "photo_queue_arn" {
  description = "ARN of the photo queue (not the dead-letter queue). The role may receive from, delete from and read the attributes of this queue only."
  type        = string
}

variable "photo_queue_url" {
  description = "URL of the photo queue. Passed to the worker as QUEUE_URL."
  type        = string
}

variable "photos_bucket" {
  description = "Name of the photos bucket. Passed to the worker as PHOTOS_BUCKET. The role may read objects under photos/ only."
  type        = string
}

variable "items_table_name" {
  description = "Name of the Items table. Passed to the worker as ITEMS_TABLE."
  type        = string
}

variable "items_table_arn" {
  description = "ARN of the Items table. The role may call UpdateItem on this table only (not its indexes)."
  type        = string
}

variable "instance_type" {
  description = "Free plan instance type (ADR 0004). c7i-flex.large has 2 vCPUs and 4 GiB. Not t3.medium, which is not on the Free plan list. Must be x86_64: the AMI is the x86_64 Amazon Linux 2023."
  type        = string
  default     = "c7i-flex.large"
}

variable "root_volume_gb" {
  description = "Size of the encrypted gp3 root volume. Holds the OS, the Python environment (CPU PyTorch) and the CLIP weights, about 6 GB. The disk is billed while the instance is stopped, so keep it small."
  type        = number
  default     = 20

  validation {
    condition     = var.root_volume_gb >= 20 && var.root_volume_gb <= 100
    error_message = "root_volume_gb must be 20 to 100 (the Amazon Linux 2023 image needs 8 GB and the model environment about 6 GB)."
  }
}

# ---------------------------------------------------------------- worker bundle

variable "worker_dir" {
  description = "Folder that holds the worker code (the repo's worker/ folder, or a staging copy). It is zipped and carried in user_data (16 KB limit, checked at plan), unpacked to /opt/mofongo/worker on first boot. Keep it to source files; do not put models or wheels in it."
  type        = string
}

variable "worker_entrypoint" {
  description = "File in worker_dir that the systemd service runs with the virtualenv's python, for example main.py. Plan fails if the file is missing from worker_dir."
  type        = string
  default     = "main.py"

  validation {
    condition     = can(regex("^[A-Za-z0-9_][A-Za-z0-9_./-]*\\.py$", var.worker_entrypoint))
    error_message = "worker_entrypoint must be a relative .py path such as main.py."
  }
}

variable "torch_requirements" {
  description = "CPU-only PyTorch packages, installed first from the PyTorch CPU wheel index (a CUDA build would add gigabytes). Pin exact versions. These two lines must agree with each other and with requirements_txt."
  type        = list(string)
  default     = ["torch==2.5.1", "torchvision==0.20.1"]
}

variable "requirements_txt" {
  description = "pip requirements for the worker, installed from PyPI after the torch packages. Pin exact versions (ADR 0005: software supply chain at first boot). For the hardened path, replace with a hash-pinned file and add --require-hashes in the bootstrap."
  type        = string
  default     = <<-EOT
    open_clip_torch==2.30.0
    Pillow==11.1.0
    boto3==1.36.0
  EOT
}

variable "clip_model_sha256" {
  description = "Optional SHA-256 of the CLIP weights file (open_clip_model.safetensors or open_clip_pytorch_model.bin from laion/CLIP-ViT-B-32-laion2B-s34B-b79K). When set, the bootstrap fails if no downloaded weights file matches it (ADR 0005: verify the model checksum). Empty skips the check."
  type        = string
  default     = ""

  validation {
    condition     = var.clip_model_sha256 == "" || can(regex("^[0-9a-f]{64}$", var.clip_model_sha256))
    error_message = "clip_model_sha256 must be empty or 64 lowercase hex characters."
  }
}

# ---------------------------------------------------------------- network

variable "allow_internet_egress" {
  description = "Option A (true, default): allow TCP 443 to 0.0.0.0/0, because SSM, SQS, CloudWatch Logs, Hugging Face and PyPI are reached through the NAT gateway. Option B (false): drop that rule; traffic can then only reach the S3 and DynamoDB prefix lists and endpoint_security_group_id. Switch only together with the interface endpoints and vendored artifacts of ADR 0005 option B."
  type        = bool
  default     = true
}

variable "endpoint_security_group_id" {
  description = "Option B only: security group of the interface endpoints (ssm, ssmmessages, ec2messages, sqs, optionally logs). When set, the tagger may send TCP 443 to it. Leave null in option A."
  type        = string
  default     = null
}

# ---------------------------------------------------------------- schedule

variable "schedule_enabled" {
  description = "Create the weekday stop and start schedules. Turn off while debugging so the instance is not stopped under you."
  type        = bool
  default     = true
}

variable "schedule_timezone" {
  description = "IANA time zone the schedule times are read in."
  type        = string
  default     = "America/New_York"
}

variable "schedule_start_cron" {
  description = "EventBridge Scheduler cron for the weekday start. Default 08:00 Monday to Friday."
  type        = string
  default     = "cron(0 8 ? * MON-FRI *)"
}

variable "schedule_stop_cron" {
  description = "EventBridge Scheduler cron for the weekday stop. Default 16:00 Monday to Friday, so the instance runs 8 hours a day (about 173 hours a month, ADR 0004). The longest stop is Friday evening to Monday morning, well inside the queue's 7-day retention."
  type        = string
  default     = "cron(0 16 ? * MON-FRI *)"
}

# ---------------------------------------------------------------- logs

variable "log_retention_days" {
  description = "How long the tagger's CloudWatch log group keeps logs."
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365], var.log_retention_days)
    error_message = "log_retention_days must be a value CloudWatch Logs accepts, for example 7, 14, 30 or 90."
  }
}
