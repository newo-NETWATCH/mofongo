variable "name_prefix" {
  description = "Prefix for every resource name, for example mofongo-dev. Resources are named <name_prefix>-vpc, <name_prefix>-public-a, <name_prefix>-nat and so on."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block of the VPC (ADR 0005: 10.0.0.0/16)."
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0))
    error_message = "vpc_cidr must be a valid IPv4 CIDR block like 10.0.0.0/16."
  }
}

variable "azs" {
  description = "Availability Zones for the subnets, in order. Subnet i of each tier goes in azs[i]. Everything stays in us-east-2 (project rule). The NAT gateway sits in the public subnet of azs[0]."
  type        = list(string)
  default     = ["us-east-2a", "us-east-2b"]

  validation {
    condition     = length(var.azs) >= 1 && length(distinct(var.azs)) == length(var.azs) && alltrue([for az in var.azs : startswith(az, "us-east-2")])
    error_message = "azs must be distinct Availability Zones in us-east-2, for example us-east-2a."
  }
}

variable "public_subnet_cidrs" {
  description = "CIDRs of the public subnets, one per entry in azs. They hold only the NAT gateway (ADR 0005): no ALB, no bastion, no instances."
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]

  validation {
    condition     = length(var.public_subnet_cidrs) == length(var.azs) && alltrue([for c in var.public_subnet_cidrs : can(cidrhost(c, 0))])
    error_message = "public_subnet_cidrs needs exactly one valid CIDR per entry in azs."
  }

  # Terraform has no cidrcontains(); test containment natively. A subnet c sits inside vpc_cidr when it
  # is no larger (its prefix length >= the VPC's) and its network address, re-masked to the VPC's prefix
  # length, equals the VPC's network address. cidrhost(x, 0) masks x to its own prefix first, so
  # cidrhost("<subnet-network>/<vpc-prefix>", 0) is the subnet's base folded into the VPC's mask.
  # try(..., false) turns any malformed CIDR into a validation failure instead of a hard error (the
  # validation above already reports invalid CIDRs with a clearer message).
  validation {
    condition = alltrue([
      for c in var.public_subnet_cidrs : try(
        tonumber(split("/", c)[1]) >= tonumber(split("/", var.vpc_cidr)[1]) &&
        cidrhost("${cidrhost(c, 0)}/${split("/", var.vpc_cidr)[1]}", 0) == cidrhost(var.vpc_cidr, 0),
        false
      )
    ])
    error_message = "Every public subnet CIDR must sit inside vpc_cidr."
  }
}

variable "private_subnet_cidrs" {
  description = "CIDRs of the private subnets, one per entry in azs. The tagger runs here with no public IP (ADR 0005)."
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]

  validation {
    condition     = length(var.private_subnet_cidrs) == length(var.azs) && alltrue([for c in var.private_subnet_cidrs : can(cidrhost(c, 0))])
    error_message = "private_subnet_cidrs needs exactly one valid CIDR per entry in azs."
  }

  # Terraform has no cidrcontains(); test containment natively, as in public_subnet_cidrs above.
  validation {
    condition = alltrue([
      for c in var.private_subnet_cidrs : try(
        tonumber(split("/", c)[1]) >= tonumber(split("/", var.vpc_cidr)[1]) &&
        cidrhost("${cidrhost(c, 0)}/${split("/", var.vpc_cidr)[1]}", 0) == cidrhost(var.vpc_cidr, 0),
        false
      )
    ])
    error_message = "Every private subnet CIDR must sit inside vpc_cidr."
  }
}

variable "flow_log_retention_days" {
  description = "How long the VPC Flow Logs log group keeps records. Short on purpose (ADR 0005): Flow Logs are the detection layer for tagger egress, and CloudWatch Logs ingestion is billed per GB."
  type        = number
  default     = 7

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365], var.flow_log_retention_days)
    error_message = "flow_log_retention_days must be a value CloudWatch Logs accepts, for example 7, 14 or 30."
  }
}
