# Infrastructure

Two Terraform root modules:

- `bootstrap/` creates one S3 bucket that stores the state for everything else. You apply it once.
- `envs/dev/` is the real stack. Every AWS resource the app uses is added here over the coming weeks.

Both sign in with the AWS CLI profile `mofongo` in us-east-2. The AWS project is on the new AWS experience, which only lets you create resources in its selected Region (us-east-2). CloudFront is the exception: it is global, so it lives in us-east-1 on its own.

## Before you start

1. The AWS CLI v2 is installed and `aws sts get-caller-identity --profile mofongo` works (Step 1 of the plan).
2. Terraform 1.11 or newer: `terraform -version`.

Signing in again: `aws login --profile mofongo` opens the browser. A sign-in lasts 12 hours and renews itself for up to 90 days without the browser; after that, run `aws login` again. If Terraform cannot read the session, add a profile that uses `credential_process = aws configure export-credentials --profile mofongo`, and point `profile` in the provider and backend blocks at it.

## One-time setup: the state bucket

From `infra/bootstrap/`:

1. `terraform init` downloads the AWS provider and creates `.terraform.lock.hcl`. Commit that file.
2. `terraform plan` shows what will be created: one bucket plus its versioning, encryption, public-access block and HTTPS-only policy.
3. `terraform apply` creates the bucket. Note the `state_bucket_name` output.
4. Move the bootstrap's own state into the bucket:
   - Wait about 15 minutes after the apply, so versioning is fully on before Terraform writes state into the bucket.
   - In `bootstrap/backend.tf`, uncomment the block and put in the bucket name.
   - Run `terraform init -migrate-state` and answer `yes`.
   - Run `terraform state list`. It should list the bucket resources, now read from S3.
   - Delete the local copies: `Remove-Item .\terraform.tfstate, .\terraform.tfstate.backup`

## The dev stack

From `infra/envs/dev/`:

1. In `backend.tf`, replace `ACCOUNT_ID` with your account number, so the name matches the `state_bucket_name` output.
2. Create your variables file in PowerShell: `Copy-Item terraform.tfvars.example terraform.tfvars`, then `notepad terraform.tfvars` and put in your email. Run `git status`: `terraform.tfvars` must not be listed.
3. Check whether a budget already exists from the console: `aws budgets describe-budgets --account-id <account-id> --profile mofongo`. If one does, read the comment at the top of `budget.tf` before going on.
4. `terraform init`, then `terraform plan`, then `terraform apply`.

Daily loop: change the code, run `terraform plan`, read every line of the diff, then run `terraform apply`. Run `terraform plan` again afterwards; it should say "No changes".

## Rules

- Never commit `*.tfstate` or `*.tfvars` files, or saved plan files. `.gitignore` already blocks them.
- Never put `force_destroy` on the state bucket. It has `prevent_destroy` so a stray `terraform destroy` cannot delete it.
- `force_destroy = true` is fine on app buckets (photos, site files) so the stack can be torn down.
