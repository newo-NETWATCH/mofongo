# 0004. CLIP on EC2 with an SQS pull

Date: 2026-10-21
Status: Accepted

## Context

- Each found item has a photo. The matcher needs tags from a fixed list of category and color words, the same words as the report form.
- The earlier plan used Amazon Rekognition. Moving away from Rekognition was one of the tasks assigned this week.
- Rekognition `DetectLabels` returns labels from its own list of names, each with a confidence score. Colors come from a separate feature. The app would have to map those names to its own words. Custom Labels would need training photos. Rekognition is on the Free plan, so the plan is not the reason for the change.
- A zero-shot CLIP model compares a photo with any list of words the app gives it. It needs no training.

## Decision

| Part | Choice |
|---|---|
| Model | open_clip ViT-B-32 with the `laion2b_s34b_b79k` weights. It scores each category and color word against the photo and keeps the best. |
| Where it runs | One EC2 instance in the default VPC. The Free plan type is `c7i-flex.large` (2 vCPUs, 4 GiB). |
| How photos arrive | S3 event, then an SQS queue with a dead-letter queue. A worker on the instance polls the queue, tags the photo and writes the tags to the item. |
| Schedule | Stopped and started on weekdays to save credits. Until the schedule exists, Owen stops it by hand. |

Why pull through SQS instead of push:
- S3 can send events to SNS, SQS, Lambda or EventBridge. None of them can push to an instance without an open inbound port, and this design has none.
- The instance is stopped part of the week. The queue holds each message until the worker starts. A queue keeps a message for 4 days by default and up to 14 days.
- S3 event notifications arrive at least once, usually in seconds. A photo can be sent twice, so tagging must be safe to repeat.
- A photo that keeps failing moves to the dead-letter queue after the set number of tries. It does not block the others. Give the dead-letter queue a longer keep time than the main queue: a message keeps its first enqueue time when it moves, so it would otherwise expire soon after it arrives. Main queue 7 days, dead-letter queue 14 days (the maximum). Alarm when the dead-letter queue is not empty.
- The queue policy lets `s3.amazonaws.com` send messages, scoped to the photos bucket with `aws:SourceArn`. Add `aws:SourceAccount` too, because a bucket ARN does not contain the project ID.

Network and access:
- The instance has a public IP and a security group with no inbound rules. The group needs an explicit outbound rule.
- Session Manager replaces SSH. The SSM Agent opens the connection outward on port 443, so there is no open port and no key pair. The instance profile needs `AmazonSSMManagedInstanceCore`.
- A Lambda inside a VPC cannot reach the internet or other AWS services without a NAT gateway or VPC endpoints. The Lambdas stay outside the VPC, so none is needed. A NAT gateway costs $0.045 per hour in us-east-2 (about $33 a month), plus $0.045 per GB.

Cost (us-east-2, approximate):
- Free plan instance types are `t3.micro`, `t3.small`, `t4g.micro`, `t4g.small`, `c7i-flex.large` and `m7i-flex.large`. `t3.medium` is not on the list. `c7i-flex.large` has the same 2 vCPUs and 4 GiB.
- From `docs/plan.md`: `c7i-flex.large` is about $67 a month left on and about $17 on the weekday schedule, paid from credits.
- 8 hours on 5 weekdays is about 173 hours a month, against about 730 always on. A stopped instance has no instance charge, but its disk still costs. Its public IPv4 address is released on stop.
- The Free plan ends on 21 Apr 2027 or when the credits run out.

Licenses (why not YOLO or MobileCLIP):

| Option | License | Result |
|---|---|---|
| open_clip ViT-B-32, `laion2b_s34b_b79k` | Code is MIT. The weights are MIT on the Hugging Face model card. | Chosen. |
| YOLO (Ultralytics) | AGPL-3.0, or an Ultralytics Enterprise License that must be requested. | Avoided. AGPL has open-source requirements the app would have to meet. |
| MobileCLIP | Code is MIT. The weights use Apple's research model license. | Avoided. That license covers non-commercial research and excludes product development. |

## Consequences

Easier:
- Tags are the exact words on the report form, so the matcher compares them directly.
- No training, no per-photo fee, no NAT gateway and no VPC endpoints.
- The queue absorbs bursts and the weekday stop.

Harder or riskier:
- Owen runs a server: updates, the worker service and the model download.
- Photos are tagged only while the instance runs. A photo posted while it is stopped waits, and so does matching, which starts when tags are written. Start the instance by hand before a demo.
- Set the main queue keep time to 7 days so a long weekend stop loses nothing (the default 4 days can be passed). Keep the instance from staying stopped longer than that. Set the visibility timeout longer than one tagging run.
- `c7i-flex` has a 40% CPU baseline and can run at 100% for 95% of the time over a day. Long runs of high CPU can lower the burst speed. Tagging comes in short bursts, which suits this.
- The model card calls this a research model. It says deployed use is out of scope and asks for thorough testing with a fixed list of classes first. The app uses a fixed word list, so test the tags on sample photos before the first release (M2). The speed per photo on 2 vCPUs is not measured yet.
- With one instance, a failure pauses tagging until it is replaced. The queue keeps the work.
- Before building, confirm the Free plan list with `aws ec2 describe-instance-types --filters Name=free-tier-eligible,Values=true`.

## Alternatives considered

| Option | Why not |
|---|---|
| Amazon Rekognition (the earlier plan) | The change was assigned this week. It also returns its own label names and colors, which the app would have to map to the form's words. Custom Labels would need training photos. |
| The model in Lambda | Lambda can run it, but a zip package is limited to 250 MB unzipped, so it needs a container image (limit 10 GB). The model would load on each cold start. New projects also start with a lower memory limit than the 10,240 MB maximum. The worker loads the model once. |
| S3 pushes to the instance, or SSH access | A push needs an open inbound port, and nothing holds the photos while the instance is stopped. SSH needs an open port and a key to keep safe. |

## Sources

Checked on 2026-10-21.

- Free plan instance types: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html
- Free plan services (EC2, Rekognition, SQS): https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html
- Rekognition `DetectLabels`: https://docs.aws.amazon.com/rekognition/latest/APIReference/API_DetectLabels.html
- Lambda limits: https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html
- NAT gateway and public IPv4 prices: https://aws.amazon.com/vpc/pricing/
- Public IP released on stop: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/using-instance-addressing.html
- Stopped instances and billing: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html
- Flex instances: https://docs.aws.amazon.com/ec2/latest/instancetypes/instance-types.html
- S3 event notifications: https://docs.aws.amazon.com/AmazonS3/latest/userguide/EventNotifications.html
- SQS retention and dead-letter queues: https://docs.aws.amazon.com/help-panel/AWSSimpleQueueService/latest/console/hp-createq-config-retention.html and https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html
- Session Manager without inbound ports: https://repost.aws/knowledge-center/systems-manager-ssh-vpc-resources
- Lambda in a VPC: https://repost.aws/knowledge-center/internet-access-lambda-function
- Queue policy conditions: https://docs.aws.amazon.com/IAM/latest/UserGuide/confused-deputy.html
- Licenses: https://huggingface.co/laion/CLIP-ViT-B-32-laion2B-s34B-b79K (model card), https://github.com/mlfoundations/open_clip, https://github.com/ultralytics/ultralytics, https://github.com/apple/ml-mobileclip/blob/main/LICENSE_MODELS
