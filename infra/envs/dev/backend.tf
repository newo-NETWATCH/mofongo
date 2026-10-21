# Where Terraform keeps the state for the dev stack.
#
# Replace ACCOUNT_ID with your account number, so the bucket matches the
# `state_bucket_name` output of infra/bootstrap. `terraform init` fails until then.
#
# Backend blocks cannot use variables, and they do not read the provider block,
# so every value, including the profile, is written out here.
# use_lockfile stops two `terraform apply` runs from changing the state at once.

terraform {
  backend "s3" {
    bucket       = "mofongo-tfstate-ACCOUNT_ID"
    key          = "dev/terraform.tfstate"
    region       = "us-east-2"
    profile      = "mofongo"
    use_lockfile = true
    encrypt      = true
  }
}
