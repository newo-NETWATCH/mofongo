# Where Terraform keeps the state for the dev stack.
#
# The bucket name contains the project's account ID, so it stays out of git.
# It lives in backend.hcl (git-ignored) and is passed in at init time:
#   terraform init "-backend-config=backend.hcl"
# Create it from backend.hcl.example with the `state_bucket_name` output of
# infra/bootstrap.
#
# Backend blocks cannot use variables, and they do not read the provider block,
# so every other value, including the profile, is written out here.
# use_lockfile stops two `terraform apply` runs from changing the state at once.

terraform {
  backend "s3" {
    key          = "dev/terraform.tfstate"
    region       = "us-east-2"
    profile      = "mofongo"
    use_lockfile = true
    encrypt      = true
  }
}
