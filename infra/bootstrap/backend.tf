# Second step of the bootstrap (see infra/README.md).
#
# The first `terraform apply` keeps state in a local file, because the bucket
# does not exist yet. After that apply:
#   1. Uncomment the block below and put in the `state_bucket_name` output.
#   2. Run `terraform init -migrate-state` and answer "yes".
#   3. Delete the local terraform.tfstate and terraform.tfstate.backup.
#
# Backend blocks cannot use variables, and they do not read the provider block,
# so every value, including the profile, is written out here.

# terraform {
#   backend "s3" {
#     bucket       = "mofongo-tfstate-ACCOUNT_ID"
#     key          = "bootstrap/terraform.tfstate"
#     region       = "us-east-2"
#     profile      = "mofongo"
#     use_lockfile = true
#     encrypt      = true
#   }
# }
