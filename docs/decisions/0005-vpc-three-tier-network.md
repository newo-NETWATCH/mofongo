# 0005. A three-tier VPC for the tagger

Date: 2026-11-11
Status: Proposed. Recommends option A (single NAT) for M2, with option B (endpoints only) as the hardened end state. One thing is left to Owen: approve the credit spend and the A-first path, because either egress option costs a comparable amount — roughly the full base $100 credit (about half of the $200 maximum) over three months. See "Egress decision".

This record replaces the "Network and access" part of 0004 (default VPC, public IP). The rest of 0004 stands.

## Context

- The supervisor asked for a proper network design. The reference is the AWS re:Post article "Building a Secure and Scalable Three-Tier Architecture on AWS using CloudFormation". It uses a VPC 10.0.0.0/16 over 2 AZs with three subnet tiers:
  - public: ALB, NAT gateways, bastion host;
  - private: EC2 app servers in an Auto Scaling group;
  - isolated: Aurora MySQL, with no 0.0.0.0/0 route.
- It also uses one NAT gateway per AZ, chained security groups (ALB, then EC2, then DB), WAFv2 on the ALB, and a bastion with SSH open to 0.0.0.0/0.
- That article describes a classic server app (ALB, EC2, Aurora). Mofongo is not one:
  - The API and the matcher are Lambdas outside the VPC.
  - DynamoDB, S3 and SQS are AWS-managed and sit outside the VPC. IAM is what gates them.
  - There is no RDS, so no database subnet is needed.
  - The only compute in a VPC is one EC2 CLIP tagger. It has no inbound traffic, is managed through SSM Session Manager, and polls SQS.
- The tagger must download the CLIP model and pip wheels from the internet on first boot.
- Project rules: everything stays in us-east-2, and nothing may need us-east-1 (no CloudFront WAF, no ACM certificate for CloudFront, no Lambda@Edge).
- The supervisor's concern: a compromised box with open outbound internet can mine crypto or send data out to a command server.

## Decision

Build a custom VPC `10.0.0.0/16` in us-east-2 with two AZs (2a and 2b), instead of the default VPC.

| Part | Choice |
|---|---|
| Public subnets | `10.0.1.0/24`, `10.0.2.0/24`. Hold only a NAT gateway (option A). No ALB, no bastion, no instances. Route 0.0.0.0/0 to the internet gateway. |
| Private subnets | `10.0.10.0/24`, `10.0.11.0/24`. The tagger lives here with no public IP. Route 0.0.0.0/0 to the NAT gateway (option A) or no default route (option B). |
| Isolated database subnets | None. There is no database in the VPC. Add them only if RDS or Aurora is ever introduced. |
| Gateway endpoints | S3 and DynamoDB, attached to the private route tables. Free. Photo and tag traffic stays on the AWS network. |
| Interface endpoints | `ssm`, `ssmmessages`, `ec2messages`, `sqs`, in the private subnets. Required for option B. Optional for A (see Cost). |
| Tagger security group | No inbound rules. Outbound: TCP 443 only. Prefix-list rules for S3 and DynamoDB, and the endpoint security group for interface endpoints. In option A the NAT path needs 443 to 0.0.0.0/0. |
| Endpoint security group | Inbound 443 from the tagger group only. |
| Logging | VPC Flow Logs (all traffic) to a CloudWatch log group with a short retention. Alarm on unusual outbound volume from the tagger. |
| Admin access | SSM Session Manager only. No bastion, no key pair, no port 22. |
| Instance | IMDSv2 required. Encrypted root volume. Instance profile limited to the one queue, the photos prefix, the Items table and SSM core. |

How the article's three tiers map to Mofongo:

| Tier | In the article | In Mofongo | In the VPC? |
|---|---|---|---|
| Presentation | ALB | CloudFront and S3 (site), API Gateway REST API with Cognito User Pools authorizer and a regional WAF (0006) | No. Managed and public. |
| Application | EC2 Auto Scaling group | Lambdas (API, matcher) and the one EC2 tagger | Lambdas no. Tagger yes, private subnet. |
| Data | Aurora in isolated subnets | DynamoDB, S3, SQS (IAM-gated) | No. Managed. |

What is dropped from the article, and why:
- **WAF on the ALB.** There is no ALB. The API is now an API Gateway REST API (0006, which supersedes 0002), so a REGIONAL AWS WAF web ACL in us-east-2 attaches to the API stage directly: the AWSManagedRulesCommonRuleSet plus a per-IP rate rule. WAF on CloudFront still needs us-east-1, which the project rules forbid, so the static site gets no WAF. The static site serves only public files and has no API behind it. Controls on the API, in order:
  - the regional WAF web ACL on the REST API stage (0006);
  - the Cognito User Pools authorizer on every method, which rejects unauthenticated calls before the Lambda runs;
  - API Gateway stage and per-method throttling;
  - request validation at the gateway for the two POST bodies (0006);
  - the budget alarm to cap cost abuse (Lambda reserved concurrency is deliberately not used: a new Free-plan account must keep 100 unreserved executions, so a reservation can fail to apply — the stage throttle above is the real request cap);
  - JSON Schema checks in the Lambda, kept as defense in depth (0006);
  - CloudFront in front of the static site only, using its default `*.cloudfront.net` domain.
- **Bastion host.** Its SSH rule open to 0.0.0.0/0 on port 22 is exactly the exposure Session Manager removes. SSM opens the connection outward on 443, so the instance needs no inbound port.
- **Aurora, the isolated tier and the ALB, Auto Scaling group (2 to 6) and per-AZ NAT.** They serve a database and a fleet that do not exist here. One tagger needs one NAT at most.

### Egress decision (recommendation below; Owen approves the spend)

| | A. Single NAT gateway | B. Endpoints only, no NAT |
|---|---|---|
| How the model and wheels arrive | Downloaded from Hugging Face and PyPI on first boot through the NAT. | Vendored into S3 (model file and wheels) and pulled through the free S3 gateway endpoint, or baked into a custom AMI. |
| General internet egress | Yes, over 443 only. | None. |
| Cost (us-east-2, approximate) | NAT about $0.045 an hour (about $33 a month) plus $0.045 per GB. Billed whether or not the instance is stopped. | No NAT. Interface endpoints about $0.01 an hour per endpoint per AZ. The tagger is one instance in one AZ, so the endpoints live in one AZ only: four endpoints is about $29 a month plus a small per-GB processing charge. A second AZ (about $58) buys resilience a single batch instance does not need, so it is not part of this design. Add a fifth endpoint (`logs`) only if the tagger ships its application logs to CloudWatch; that is about $7 a month more. |
| Build effort | Low. Matches the article. | Higher: a vendoring step, pinned wheel hashes, a model checksum, or an AMI pipeline. |
| Main residual risk | A compromised tagger can reach the internet (crypto-mining, command-and-control, data exfiltration) because egress to any host on 443 is still allowed. | Supply-chain risk moves to the vendoring step. A tampered artifact in S3 would be loaded. |

**Recommendation: build A first, with B as the documented hardened end state.** The deciding factor is build effort and M2 timing, not monthly cost. In B the interface endpoints *replace* the NAT rather than add to it, and because the tagger is a single instance in one AZ, one AZ of endpoints (about $29 a month) costs about the same as the NAT (about $33 a month plus data). So the two options spend a comparable share of the credits; A simply gets the tagger working for M2 with the least build effort, and B is the answer to the supervisor's exfiltration concern.

The earlier draft treated the endpoints as a $30-$58 charge *on top of* the NAT. That is only true if you run both at once, which no option here does. Corrected: A is NAT-only, B is endpoints-only, and their monthly costs are close.

On adding the interface endpoints now: in A they are **optional**, because SSM and SQS traffic reaches AWS through the NAT. In B they are **required**, because there is no other path. So "add the endpoints" and "move to B" are the same step. Build A without them, and add all four (ssm, ssmmessages, ec2messages, sqs) in the single commit that deletes the NAT for B. In B, launch the tagger in the same AZ as the endpoints (they live in one AZ for cost); otherwise its traffic crosses AZs, which adds data charges and loses the AZ isolation the second private subnet implies.

Notes on A:
- Restricting egress to 443 and denying all inbound does not stop outbound C2 traffic on 443. It narrows the surface. Flow Logs and the outbound-volume alarm are the detection layer. This gap is exactly what B closes, which is why B stays on the roadmap and is not dropped.
- The lever that actually saves credits is not A-vs-B but teardown. The NAT (option A) and the interface endpoints (option B) are both billed around the clock, so neither benefits from the instance's weekday schedule on its own. To save credits, have Terraform create and destroy the NAT (A) or the endpoints (B) on the same weekday schedule as the instance. This adds moving parts, so decide it when the schedule is built.

What is left for Owen to approve before `terraform apply`, not a design choice:
- The credit spend. Either option runs about $90-100 over three months — roughly the full base $100 credit, or about half of the $200 maximum — so confirm A-first is acceptable, or ask to start on B.
- Free-plan support. Confirm the Free plan accepts NAT gateways (A) and interface endpoints (B): `aws freetier get-account-plan-state --profile mofongo --region us-east-1`, then the supported-services list. If NAT is not covered, that is itself a reason to start on B; if interface endpoints are not covered either, raise it before building.
- The prices above are approximate and were not re-checked live. Re-read the VPC pricing page for us-east-2 at build time and put the real numbers in the Terraform plan review.

## Consequences

Easier:
- The tagger has no public IP and no inbound path, and the network is defined in Terraform instead of inherited from the default VPC.
- S3 and DynamoDB traffic never leaves the AWS network and costs nothing extra.
- Flow Logs give a record of every connection the tagger makes.
- Moving from A to B is deleting the NAT and its route, because the endpoints and the vendored artifacts are the only additions.

Harder or riskier:
- Either egress option costs about $29 to $33 a month plus data, against about $100 in base credits (up to $100 more). Over three months that is roughly the full base $100 credit, or about half of the $200 maximum. The Free plan ends on 21 Apr 2027 or when the credits run out. Confirm NAT gateways (A) and interface endpoints (B) are accepted on the Free plan before building (`aws freetier get-account-plan-state`, then the supported-services list).
- A NAT gateway (A) and interface endpoints (B) are both billed while the instance is stopped. The weekday schedule saves instance hours only; see the teardown note under "Egress decision".
- The reference design has no equivalent for the Lambdas. A Lambda placed in this VPC would need the NAT or endpoints, so keep them outside it, as 0004 states.
- A single NAT is a single point of failure for the AZ it sits in. That is acceptable for a batch tagger whose work waits in SQS.

Trust boundaries and residual risks:
- **Internet to API Gateway and CloudFront.** Untrusted users. Controls: on the API, a regional WAF (common rule set and per-IP rate rule), the Cognito User Pools authorizer, throttling, gateway and Lambda schema checks, and least-privilege Lambda roles (0006). Residual: the static site on CloudFront has no WAF (it needs us-east-1), and the API's WAF rate rule is per IP, so many users behind one address share a limit and an attacker with many addresses is not slowed. Cost abuse is limited by throttling and the budget alarm.
- **User uploads to S3 to the tagger.** Photos are untrusted input that a Python image decoder parses on the instance. A decoder bug could give code execution on the tagger. Controls: keep image libraries pinned and updated, cap file size and type at upload, run the worker as a non-root user, scope the instance role to one queue, one prefix and one table. Residual: a compromised tagger can still write tags to Items and read photos. The matcher should treat tags as untrusted and accept only words from the fixed list.
- **Tagger to the internet (option A).** Described above. Residual until B.
- **Software supply chain at first boot.** Model and wheels come from Hugging Face and PyPI. Pin versions and hashes (`--require-hashes`) and verify the model checksum in A as well as B.
- **Operator to the instance.** Session Manager sessions are IAM-authenticated and can be logged to CloudWatch or S3. Restrict who can call `ssm:StartSession`. No SSH keys exist to leak.
- **Instance metadata.** IMDSv2 only, so a request-forwarding bug cannot read the role credentials with a simple GET.

## Alternatives considered

| Option | Why not |
|---|---|
| Keep the default VPC with a public IP (0004) | The public IP and the default VPC's open public subnets do not meet the supervisor's request for a defined network. The instance's own outbound path is no better controlled. |
| Copy the article in full (ALB, Auto Scaling group, Aurora, bastion, WAF, NAT per AZ) | It would build a database, load balancer and fleet the app does not use, cost several times more, and add the bastion SSH exposure. |
| Put the Lambdas in the VPC | They would need NAT or endpoints for every AWS call and gain nothing, since DynamoDB, S3 and SQS are already IAM-gated (0004). |
| WAF on CloudFront | Needs us-east-1, which the project rules forbid. The static site does not need it. |
| WAF on a REST API | Adopted. 0006 moved the API to a REST API, so a regional WAF attaches to its stage in us-east-2. |
| NAT gateway per AZ | Doubles the cost for resilience a single batch instance does not need. |
| Isolated DB subnets anyway | They would hold nothing. Add them with the first VPC-bound database. |

## Sources

Referenced on 2026-11-11. Prices are approximate from AWS pricing pages and earlier records and were not re-checked live. Check them again before relying on them.

- Reference article: AWS re:Post, "Building a Secure and Scalable Three-Tier Architecture on AWS using CloudFormation" (search the title at https://repost.aws/)
- NAT gateway, interface endpoint and public IPv4 prices: https://aws.amazon.com/vpc/pricing/
- Gateway endpoints for S3 and DynamoDB (no charge): https://docs.aws.amazon.com/vpc/latest/privatelink/gateway-endpoints.html
- Endpoints Session Manager needs without internet access: https://repost.aws/knowledge-center/ec2-systems-manager-vpc-endpoints
- Resources AWS WAF can protect (REST API stages yes, HTTP APIs no): https://docs.aws.amazon.com/waf/latest/developerguide/waf-chapter.html
- WAF with API Gateway REST API stages: https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-control-access-aws-waf.html
- WAF on CloudFront is created in us-east-1: https://docs.aws.amazon.com/waf/latest/developerguide/how-aws-waf-works-resources.html
- API Gateway REST API throttling: https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-request-throttling.html
- VPC Flow Logs: https://docs.aws.amazon.com/vpc/latest/userguide/flow-logs.html
- IMDSv2: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html
- Session Manager without inbound ports: https://repost.aws/knowledge-center/systems-manager-ssh-vpc-resources
- Project records: 0002 (HTTP API, superseded), 0006 (REST API and WAF), 0004 (tagger on EC2 with SQS pull), `docs/plan.md` Parts 1 and 3
