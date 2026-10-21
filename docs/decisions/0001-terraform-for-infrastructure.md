# 0001. Terraform for infrastructure

Date: 2026-10-21
Status: Accepted

## Context

- The earlier plan set up every AWS resource by hand in the AWS Management Console.
- Owen's supervisor asked for infrastructure as code this week.
- The AWS project is on the Free plan and has limited credits, so the stack must be easy to rebuild and to delete.
- Everything stays in us-east-2, the project's selected Region.

## Decision

Write all AWS infrastructure in Terraform. Keep the Terraform state in an S3 bucket and use S3 native locking (`use_lockfile = true`). There is no DynamoDB lock table. Terraform now marks DynamoDB locking as deprecated.

| Folder | What it does |
|---|---|
| `infra/bootstrap/` | Creates the state bucket once. The bucket has versioning, encryption, a public-access block, an HTTPS-only policy and `prevent_destroy`. After the first apply, its own state moves into the bucket. |
| `infra/envs/dev/` | The real stack. Every other resource is added here. Its state key is `dev/terraform.tfstate`. |

- The split exists because the bucket must exist before any stack can keep state in it. It also keeps a stray `terraform destroy` in `dev` away from the bucket.
- There is one AWS provider, in us-east-2, using the CLI profile `mofongo` (`aws login`). No access keys are created.
- CloudFront is global. Terraform manages it from the same us-east-2 provider.
- S3 native locking was added in Terraform 1.10 and became generally available in 1.11. This project requires 1.11 or newer.

## Consequences

Easier:
- Every change shows as a diff in `terraform plan` before `terraform apply`.
- The whole stack can be rebuilt or destroyed from the code.
- Infrastructure changes go through git, so they can be reviewed.
- There is no lock table to create or pay for.

Harder or riskier:
- The state file is plain text and can hold secret values. Never commit it. The bucket is private and encrypted, but it keeps old versions of the state, and those hold the same secrets.
- If the state is lost, Terraform forgets what it built. The bucket has `prevent_destroy`. Never put `force_destroy` on it.
- Backend blocks cannot use variables. The Region and profile are written out in each backend block. The bucket name contains the account ID and the repo is public, so it lives in a git-ignored `backend.hcl` passed with `terraform init "-backend-config=backend.hcl"`.
- The lock needs permission to read, write and delete a lock file in the bucket (`s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`).
- Anything built by hand earlier must be imported or deleted before week 2, or Terraform will clash with it.
- Owen is new to Terraform. Step 3 of the plan is set aside for learning it.

## Alternatives considered

| Option | Why not |
|---|---|
| Console by hand (the earlier plan) | Nothing is written down, so it cannot be reviewed or repeated. The supervisor asked for infrastructure as code. |
| CloudFormation | It would also meet the supervisor's request and works on the Free plan. It tracks the stack inside AWS, so there is no state file to protect. Not chosen because the project is already set up around Terraform (Steps 1 to 3 of the plan). |
| CDK | It builds on CloudFormation. It needs a one-time bootstrap in each Region that creates an S3 bucket, an ECR repository and IAM roles, and it adds a programming-language toolchain. Not chosen for the same reason as CloudFormation. |

## Sources

Checked on 2026-10-21.

- Terraform S3 backend: https://developer.hashicorp.com/terraform/language/backend/s3
- Secrets in state: https://developer.hashicorp.com/terraform/language/state/sensitive-data
- Terraform 1.11 changelog: https://github.com/hashicorp/terraform/blob/v1.11/CHANGELOG.md
- AWS guidance on S3 locking: https://docs.aws.amazon.com/prescriptive-guidance/latest/terraform-aws-provider-best-practices/backend.html
- CDK bootstrapping: https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping-env.html
- Free plan services (CloudFormation is listed): https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html
