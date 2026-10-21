# Mofongo: project rules

## Guidance level: medium

- Do what Owen asks.
- Ask at most two clarifying questions per task, and only when the request is ambiguous or something looks wrong.
- Don't repeat a question or suggestion Owen has already turned down.
- Don't explain trade-offs or alternatives unless Owen asks. Always flag security risks.

## Wording (new AWS experience)

- Say "project", not "account". A project contains the AWS account plus its sharing settings.
- Say "team member", not "IAM user". Team members are invited by email, not created in IAM.
- Say "AWS Settings" (settings.aws.com) for billing, spend limits, team members and projects. Resources themselves are in the AWS Management Console.
- Say "selected Region", not "home Region".

## Region: everything stays in us-east-2

- Create every resource in us-east-2, and pass us-east-2 on every CLI, SDK and MCP call (`--region us-east-2`, `region_name="us-east-2"`).
- Terraform has one AWS provider, in us-east-2. Never add a us-east-1 provider alias.
- CloudFront is global. Manage it from the us-east-2 provider and use its default `*.cloudfront.net` domain.
- Don't use anything that would need us-east-1:
  - an ACM certificate for a CloudFront custom domain
  - AWS WAF on CloudFront
  - Lambda@Edge
- Don't use cross-Region features:
  - S3, DynamoDB or RDS replication
  - DynamoDB global tables
  - multi-Region KMS keys
  - CloudFormation StackSets
  - Route 53 latency, geolocation or failover routing
- The only us-east-1 endpoint in use is the AWS Agent Toolkit / AWS MCP Server, which creates nothing. Its calls default to us-east-2.

## The AWS project

- Sign in with `aws login --profile mofongo`. A sign-in lasts 12 hours and renews itself for up to 90 days. Never create or ask for access keys.
- Free plan: $100 in credits, with up to $100 more to earn. It ends on 21 Apr 2027 or when the credits run out, whichever comes first.
  - Keep EC2 on the weekday schedule so the credits last.
  - Use Free plan instance types (c7i-flex.large for the tagger, not t3.medium).
- If a service refuses to work, run `aws freetier get-account-plan-state --profile mofongo --region us-east-1`, then check AWS's supported-services lists for the Free and Paid plans.
- If something that used to work suddenly returns AccessDenied, ask whether a spend limit was hit. Owen checks this in AWS Settings > Billing.
- At the end of a task that created AWS resources, ask whether to keep them or clean them up.
- Before an AWS task, check whether an AWS skill covers it (`~/.claude/skills/aws-*`, or `retrieve_skill` through the AWS MCP Server), and prefer its guidance.
