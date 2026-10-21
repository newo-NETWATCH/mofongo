# Mofongo groundwork plan (Terraform): learn first, app later

## Answer these first

1. ~~Free plan or Paid plan?~~ Answered: **Free plan** (AWS welcome email, 20 Oct 2026). It comes with $100 in credits, with up to $100 more to earn, and ends on 21 Apr 2027 or when the credits run out. The project uses the new AWS experience (social sign-in, selected Region us-east-2), so everyday sign-in is `aws login` and IAM Identity Center does not apply.
2. ~~Anything built by hand in the console?~~ Answered: **nothing.** The project only finished activation on 21 Oct 2026, and it had no buckets, tables or budgets before the bootstrap. Nothing needs importing.
3. ~~Repo folder and GitHub account?~~ Answered: `C:\SEC_PROJ\mofongo`, public at https://github.com/newo-NETWATCH/mofongo.
4. ~~Which week?~~ Answered: **week 1**, starting 20 Oct 2026.
5. ~~HTTP API with body checks in the Lambda, instead of a REST API?~~ Answered: **yes** (21 Oct 2026). Recorded in `docs/decisions/0002-http-api-with-validation-in-lambda.md`.

## Part 1. What this week's changes mean

**SNS + Lambda instead of SES**
- **Design:** one SNS topic. When an owner files a lost report, the API Lambda subscribes their email to it, with a filter policy on their user ID. The email is read from the `email` claim of the Cognito ID token, and only if `email_verified` is true. When a match is found, the matching Lambda publishes with that user ID attached, so only that owner receives it.
- **The owner's side:** they click "Confirm subscription" once, in an email from "AWS Notifications", within 48 hours. After that, emails are plain text from no-reply@sns.amazonaws.com, and every one has a one-click unsubscribe link.
- **Privacy:** a subscription without a filter policy receives every message on the topic.
- **Limits and cost:** filter changes take up to 15 minutes to apply, and there is a default limit of 200 filter policies per topic. Cost is about $0, since 1,000 emails a month are free.
- **Expect to be asked:** AWS itself recommends SES for app email, so have your reason ready.

**Open-source model on EC2 instead of Rekognition**
- **Model:** open_clip ViT-B-32, laion2b weights (MIT code and weights). It compares each photo with the exact category and color words from the report form, with no training.
- **Pull design:** a photo upload makes S3 send an event to an SQS queue, which has a dead-letter queue for photos that keep failing. A worker on EC2 polls the queue, tags the photo and writes the tags to DynamoDB.
- **Network:** the instance runs in the default VPC with a public IP, no inbound rules and SSM Session Manager instead of SSH. The Lambdas stay outside the VPC, so no NAT gateway (about $33 a month) is needed.
- **Instance and cost:**
  - Paid plan: t3.medium, about $36 a month left on, or about $10 if it runs only 8 hours on weekdays.
  - Free plan (this project): t3.medium is not allowed. Use c7i-flex.large (4 GiB), about $67 a month left on or about $17 on the weekday schedule, paid from credits. Keep it on the schedule: the Free plan ends when the credits run out.
- **Avoid:** YOLO (AGPL license) and MobileCLIP (research-only weights).

**Infrastructure as code**
- Terraform (you have v1.16.5) with its state in S3 and S3 native locking (`use_lockfile = true`, needs 1.11 or newer).
- The state file can hold secrets: never commit it, and never let `destroy` reach the state bucket.

**API schemas**
- HTTP APIs cannot check request bodies at all. So keep one JSON Schema file per request body in the repo and check it inside the Lambda.
- Write the schemas in the draft-4 subset, so they could move to a REST API later.

**Matching now runs both ways.** DynamoDB Streams on Items and on Reports both start the matching Lambda:
- A new tagged item is checked against open reports.
- A new report is checked against listed items.
- A Matches table stops the same pair being emailed twice.

The earlier design only matched new items, so a report filed after the item was posted was never matched.

**New service list:** S3 (site files, photos), CloudFront, Cognito, API Gateway (HTTP API), Lambda (API, matching), DynamoDB with Streams, SQS (queue, dead-letter queue), EC2 in the default VPC, SNS, Systems Manager (Session Manager), IAM, CloudWatch, Budgets. SES, Rekognition and the "process photo" Lambda are gone.

## Part 2. The plan

### Step 1. Project sign-in and tools (about 3 hours)

Learn: projects in the new AWS experience, browser sign-in with `aws login`, Free vs Paid plan, the selected Region.

Do:
1. Check the plan and remaining credits (question 1). Billing, spend limits and team members are managed in AWS Settings (settings.aws.com); budgets live in the Billing and Cost Management console.
2. Turn on two-step verification for the Google or GitHub account you sign in to AWS with.
3. Confirm the project's selected Region in AWS Settings > View all projects > Overview > Additional Info > Region. It is us-east-2, and Regional resources (Lambda, API Gateway, DynamoDB, S3, EC2) can only be created there.
4. Install the AWS CLI v2 (done: 2.38.3, per-user install) and sign in:
   - `aws configure set region us-east-2 --profile mofongo`, then `aws login --region us-east-2 --profile mofongo`. Approve in the browser. No access keys are ever created.
   - A sign-in lasts 12 hours and renews itself for up to 90 days without the browser.
   - If Terraform cannot read that session, add a profile that uses `credential_process = aws configure export-credentials --profile mofongo`.
5. Check the Budgets alert. Make it count spending before credits, or it stays at $0 while credits quietly pay for EC2. Set the amount to fit your EC2 choice.
6. Install the HashiCorp Terraform extension for VS Code.
7. Before the EC2 week: install the Session Manager plugin for the AWS CLI.

Done when: `aws sts get-caller-identity --profile mofongo` prints your project's account ID and an ARN, and two-step verification is on for your sign-in provider.

### Step 2. The repo (about 1 to 2 hours)

Learn: commit, branch, pull request, and what must never be committed (state, `.tfvars`, `.env`, AWS credentials).

Do:
1. Create the folder and run `git init` (your git name and email are already set).
2. Before the first commit, add a `.gitignore`: `.terraform/`, `*.tfstate`, `*.tfstate.*`, `*.tfplan`, `crash.log`, `*.tfvars`, `*.tfvars.json`, `.env`, `.venv/`, `__pycache__/`, `build/`, `*.zip`. Do commit `.terraform.lock.hcl`. Also add a `.gitattributes` with `* text=auto eol=lf`, so files that run on Linux keep Linux line endings.
3. Create this layout, with a one-line README.md in each folder (git does not track empty folders):
```
mofongo/
  infra/bootstrap/   state bucket, created once
  infra/envs/dev/    the real stack
  infra/modules/     added later
  api/openapi.yaml   list of endpoints
  api/schemas/       one JSON Schema per request body
  backend/           Lambda code (api, matcher)
  worker/            EC2 tagger
  web/               frontend, later
  docs/              architecture, data model, decisions
```
4. Make the first commit, then run `gh repo create mofongo --private --source . --push`.

Done when: GitHub shows every folder plus the `.gitignore`, and `git status` says "nothing to commit, working tree clean".

### Step 3. Terraform foundations (about 5 to 8 hours)

Learn: do HashiCorp's "Get Started - AWS" tutorial in a throwaway folder, then destroy what it creates. It covers providers, resources, plan, apply, destroy, state, variables and outputs. Two changes from the tutorial:
- Skip its access-key exports. Sign in as in Step 1, then run `$env:AWS_PROFILE = "mofongo"` in PowerShell.
- Change `t2.micro` to `t3.micro`.

Then read about modules and the S3 backend.

Do:
1. In `infra/bootstrap`, create the state bucket:
   - Name it `mofongo-tfstate-<your project's 12-digit account ID>`, since bucket names must be unique worldwide.
   - Turn on versioning and encryption, and block all public access.
   - Add `lifecycle { prevent_destroy = true }`.
   - Apply with local state.
2. Add a `backend "s3"` block to the bootstrap: `key = "bootstrap/terraform.tfstate"`, region, profile and `use_lockfile = true`. The bucket name contains the account ID, and the repo is public, so it goes in a git-ignored `backend.hcl` instead. Run `terraform init -migrate-state "-backend-config=backend.hcl"` and answer yes, then delete the local `terraform.tfstate` and `terraform.tfstate.backup`.
3. In `infra/envs/dev`, set up three things:
   - `required_version = ">= 1.11"`.
   - The AWS provider: region us-east-2, profile `mofongo`, and `default_tags` Project=mofongo, Env=dev.
   - A `backend "s3"` block with `key = "dev/terraform.tfstate"`, `region = "us-east-2"`, `profile = "mofongo"`, `use_lockfile = true` and `encrypt = true`, plus `bucket` in a git-ignored `backend.hcl`. Write every value out literally: backend blocks cannot use variables and do not read the provider's settings.
4. Put the budget in code with `cost_types { include_credit = false }`. Either delete the console budget and write it fresh, or bring it in with an `import` block (`id = "<account ID>:<budget name>"`) and set `name` to the console budget's exact name, since renaming a budget replaces it.
5. Practice the loop: change a tag, `plan`, read the diff, `apply`, `plan` again.

Done when: `plan` in `envs/dev` says "No changes", both state files are in the bucket, and no `.tfstate` file is left on your laptop.

### Step 4. Designs on paper (about 6 to 10 hours)

Learn: DynamoDB partition and sort keys, global secondary indexes (including sparse ones), Query vs Scan, JSON Schema draft 4, and HTTP status codes.

Do:
1. List the screens: browse, item detail, post item, file report, my reports, report detail, alert status. Then list the access patterns (Part 3).
2. Write `docs/data-model.md`.
3. Write `api/openapi.yaml` and one JSON Schema per request body in `api/schemas/`.
4. Write four short decision records in `docs/decisions/`: Terraform, HTTP API with validation in Lambda, SNS email, CLIP on EC2 with the pull design.

Done when: every screen maps to an endpoint, every endpoint to an access pattern, and every access pattern to a key or an index, with no Scan.

### Step 5. Update the project documents (about 1 to 2 hours)

**Status (21 Oct 2026):** item 1 is done (both diagrams show the new design). Items 2 and 3 are dropped by Owen's choice: the deck and the written pitch keep the earlier design.

1. Redraw both draw.io diagrams for the new design: SQS and its dead-letter queue, the EC2 tagger in the default VPC, both streams, the matching Lambda and SNS.
2. Update the services and timeline slides.
3. Update the written pitch: it says "set up by hand in the AWS console", and it describes matching in one direction only.

Done when: no diagram, slide or the pitch mentions SES, Rekognition, the "process photo" Lambda, or setup by hand.

## Part 3. Draft designs for Step 4

| Endpoint | Does |
|---|---|
| `GET /items` | Browse listed items, newest first, optionally by category |
| `POST /items` | Post a found item. Returns the item ID and a presigned POST for the photo, limited to 10 MB, saved as `photos/{itemId}.jpg` |
| `GET /items/{itemId}` | One item, with a short-lived photo view link |
| `POST /items/{itemId}/returned` | Mark returned (the finder only) |
| `POST /reports` | File a lost report and subscribe the owner's email |
| `GET /reports` | My reports |
| `GET /reports/{reportId}` | One report and its matches (the owner only) |
| `GET /me/alerts` | Email alerts pending, confirmed, or none |

How `GET /me/alerts` works: the subscription ARN is saved in Users when subscribing (use `ReturnSubscriptionArn`). The endpoint then reads it and asks SNS for the subscription's status. "Not found" means the subscription expired or the user unsubscribed, so offer to subscribe again.

Every endpoint sits behind the Cognito JWT authorizer, and the web app sends the ID token.

| Access pattern | Answered by |
|---|---|
| All listed items, newest first | Items, sparse index ListedByDate: `listedPk = "LISTED"` + `createdAt`. The attribute only exists while the item is listed, so returned items drop out of the index by themselves. |
| Listed items in one category, newest first | Items, sparse index ListedByCategory: `listedCategory` + `createdAt` |
| One item; save tags; mark returned | Items, key `itemId` |
| Open reports in a category (matching) | Reports, sparse index OpenByCategory: `openCategory` + `createdAt` |
| My reports | Reports, index ByOwner: `ownerId` + `createdAt` |
| A report's matches; "already emailed?" | Matches, key `reportId` + `itemId` (conditional write) |
| A user's email subscription | Users, key `userId` (the Cognito sub) |

All tables use on-demand billing. Streams are on for Items and Reports, with filters so the matching Lambda only runs in two cases: an item gains tags while it is listed, or a report is created.

Things that commonly trip people up later:
- **SQS queue policy:** it must let `s3.amazonaws.com` send messages, scoped to the photos bucket with `aws:SourceArn`.
- **EC2 outbound rule:** a Terraform security group needs an explicit outbound (egress) rule. Without it the instance cannot reach SSM, SQS or S3.
- **EC2 instance profile:** it needs AmazonSSMManagedInstanceCore.
- **Lambda dependencies:** build them for Linux, because Windows builds fail on Lambda: `pip install --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.13 -t build/api <package>`.
- **`force_destroy`:** use it only on app buckets, never on the state bucket.

## Part 4. Revised 8-week timeline

| Week | Work | Milestone |
|---|---|---|
| 1 | Steps 1 to 3, start Step 4 | |
| 2 | Terraform: DynamoDB tables, Cognito, HTTP API with JWT authorizer, API Lambda with schema checks | |
| 3 | Terraform: photos bucket with upload and view links, SQS with dead-letter queue, SNS topic, reports subscribe the owner. A placeholder page on S3 and CloudFront with Cognito login working end to end | M1: core backend and infrastructure |
| 4 | EC2 tagger: instance, worker service, CLIP, stop and start schedule (stop the instance by hand until the schedule exists) | |
| 5 | Browse items, post an item with a photo | M2: first release |
| 6 | Matching both ways through the streams, SNS email, lost report page | |
| 7 | Mark as returned, fixes, buffer | M3: features done |
| 8 | Testing, demo, final report | M4: final demo |

Weeks 4 and 5 carry the most risk. If the tagger runs late, M2 ships the upload without tags.
