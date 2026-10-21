# Second step of the bootstrap (see infra/README.md).
#
# The first `terraform apply` kept state in a local file, because the bucket
# did not exist yet. This block then moves the state into that bucket.
#
# The bucket name contains the project's account ID, so it stays out of git.
# It lives in backend.hcl (git-ignored) and is passed in at init time:
#   terraform init -migrate-state "-backend-config=backend.hcl"
# Create it from backend.hcl.example with the `state_bucket_name` output.
#
# Backend blocks cannot use variables, and they do not read the provider block,
# so every other value, including the profile, is written out here.

terraform {
  backend "s3" {
    key          = "bootstrap/terraform.tfstate"
    region       = "us-east-2"
    profile      = "mofongo"
    use_lockfile = true
    encrypt      = true
  }
}
