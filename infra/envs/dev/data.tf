data "aws_caller_identity" "current" {}

locals {
  name_prefix = "mofongo-dev"
  account_id  = data.aws_caller_identity.current.account_id

  # envs/dev -> repo root. scripts/build-api.ps1 writes the package to build/api.
  api_package_dir = coalesce(var.api_package_dir, abspath("${path.module}/../../../build/api"))
}
