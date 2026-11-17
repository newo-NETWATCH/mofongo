# The tagger's instance role. Least privilege: every statement names one resource, none uses
# Resource "*" except where the action has no resource-level form (noted inline).
# Access is by the instance profile through IMDSv2. There are no access keys anywhere.

data "aws_iam_policy_document" "assume" {
  statement {
    sid     = "Ec2AssumesRole"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }

    # Confused deputy guard: only EC2 in this project may assume the role.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "tagger" {
  name               = "${local.instance_name}-ec2"
  description        = "Instance role of the ${local.instance_name} EC2 instance. Least privilege, see ADR 0004 and docs/data-model.md section 4.1."
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# Session Manager (ADR 0004). AWS-managed, and the only managed policy on this role.
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.tagger.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "tagger" {
  # Poll the photo queue and delete a message once its photo is tagged. ChangeMessageVisibility
  # lets the worker hand back a message it will not finish. The dead-letter queue is not listed:
  # SQS moves messages there itself.
  statement {
    sid = "PollPhotoQueue"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:GetQueueAttributes",
    ]
    resources = [var.photo_queue_arn]
  }

  # Download the photo. photos/* only. The bucket uses SSE-S3 (AES256), so no kms:Decrypt.
  # No s3:ListBucket: a missing key then reads as AccessDenied, which the worker treats as an
  # error and retries into the dead-letter queue, not as a silent skip.
  statement {
    sid       = "ReadPhotos"
    actions   = ["s3:GetObject"]
    resources = ["arn:${data.aws_partition.current.partition}:s3:::${var.photos_bucket}/photos/*"]
  }

  # Write clipTags, tagStatus, taggedAt and tagError on an item (data-model 4.1). UpdateItem
  # only, on the table ARN only, not its indexes. The worker's update is conditional, so it needs
  # no GetItem, PutItem or DeleteItem.
  statement {
    sid       = "WriteItemTags"
    actions   = ["dynamodb:UpdateItem"]
    resources = [var.items_table_arn]
  }

  # The CloudWatch agent ships /var/log/mofongo/*.log to the log group Terraform created.
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
    resources = ["${aws_cloudwatch_log_group.tagger.arn}:*"]
  }

  # The agent checks that its log group exists before it writes. DescribeLogGroups has no
  # resource-level form for one group, so it is limited to log groups in this project and Region.
  statement {
    sid       = "AgentChecksLogGroup"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["arn:${data.aws_partition.current.partition}:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:*"]
  }
}

resource "aws_iam_role_policy" "tagger" {
  name   = "tagger"
  role   = aws_iam_role.tagger.id
  policy = data.aws_iam_policy_document.tagger.json
}

resource "aws_iam_instance_profile" "tagger" {
  name = "${local.instance_name}-ec2"
  role = aws_iam_role.tagger.name
}
