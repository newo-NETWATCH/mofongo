terraform {
  # 1.11 is the first version where S3 native state locking (use_lockfile)
  # is generally available.
  required_version = ">= 1.11"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile

  # Added to every resource this provider creates, so the AWS console and the
  # bill can be filtered by project.
  default_tags {
    tags = {
      Project   = "mofongo"
      Stack     = "bootstrap"
      ManagedBy = "terraform"
    }
  }
}
