# Decision records

Short notes on each design choice and why it was made. Each one answers "why was it done this way?" for someone reading the project later.

## The records

| Record | Decision in one line | Status |
|---|---|---|
| [0001](0001-terraform-for-infrastructure.md) | Build all AWS infrastructure with Terraform. State lives in S3 with S3 native locking. | Accepted |
| [0002](0002-http-api-with-validation-in-lambda.md) | Use an API Gateway HTTP API with a Cognito JWT authorizer. The Lambda checks each request body against a draft-4 JSON Schema. | Accepted |
| [0003](0003-sns-for-match-emails.md) | Send match emails through one SNS topic. Each owner's email subscription has a filter policy on their user ID. | Accepted |
| [0004](0004-clip-on-ec2-with-sqs-pull.md) | Tag photos with open_clip ViT-B-32 on one EC2 instance. It pulls photos from an SQS queue fed by S3 events. | Accepted |

## Format

Each record is one Markdown file named `NNNN-short-title.md`. The number is never changed or reused. Keep it to about one page.

| Part | What goes in it |
|---|---|
| Title | `# NNNN. Short title` |
| Date and Status | The date it was written, and `Accepted` or `Superseded by NNNN`. |
| Context | The situation and what forced a choice. Facts only. |
| Decision | What was chosen, in short sentences. |
| Consequences | Two lists: what gets easier, and what gets harder or riskier. |
| Alternatives considered | One or two lines on why each other option was not chosen. |
| Sources | Links to the AWS or project pages that the limits, times, prices and licenses came from. |

## Rules

- Check every limit, time window, price and license against its source page when you write the record.
- Write prices as approximate and name the Region (us-east-2). Prices change, so check again before you rely on one.
- Do not rewrite the decision in an accepted record. If the choice changes, write a new record and set the old one to `Superseded by NNNN`.
- Fixing a typo or a dead link is fine.

## Adding a record

1. Copy the newest record and give it the next number.
2. Fill in each part of the format above.
3. Add a row to the table at the top of this file.
