# The photo queue: S3 sends one message per uploaded photo, and the tagger on EC2 pulls them.
# Spec: docs/decisions/0004-clip-on-ec2-with-sqs-pull.md. Standard queue (S3 events arrive at
# least once, so the worker tags idempotently) with a dead-letter queue.
#
# This module creates the two queues, the main queue's policy and the DLQ alarm. It does NOT
# create the S3 bucket notification (bucket -> queue): envs/dev wires that, so this module and
# photos_bucket never depend on each other. The tagger's own IAM (ReceiveMessage, DeleteMessage,
# ChangeMessageVisibility, GetQueueAttributes on queue_arn) belongs to the tagger module; an
# identity policy in the same account needs no statement in the queue policy below.

locals {
  queue_name = "${var.name_prefix}-photos"
  dlq_name   = "${var.name_prefix}-photos-dlq"
}

# ---------------------------------------------------------------- dead-letter queue

# Keeps messages that failed max_receive_count times. 14 days is the SQS maximum. A moved
# message keeps its ORIGINAL enqueue time, so the DLQ must keep longer than the main queue
# (7 days) or a message would expire soon after it arrives (ADR 0004).
resource "aws_sqs_queue" "dlq" {
  name                      = local.dlq_name
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true
}

# Only the main queue may use this queue as its dead-letter queue.
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.photos.arn]
  })
}

# ---------------------------------------------------------------- main queue

# message_retention_seconds is 7 days (default is 4) so a long weekend with the instance stopped
# loses nothing. Keep the instance from staying stopped longer than that. Long polling (20 s)
# cuts empty receives. SSE uses the SQS-owned key, so S3 can send without any KMS key policy.
resource "aws_sqs_queue" "photos" {
  name                       = local.queue_name
  message_retention_seconds  = 604800 # 7 days
  visibility_timeout_seconds = var.visibility_timeout_seconds
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

# Two statements:
#   1. Allow ONLY the S3 service principal to SendMessage, and only for events from the photos
#      bucket (aws:SourceArn) in this project (aws:SourceAccount). Both conditions: the bucket
#      ARN has no account ID, so SourceArn alone could match a same-named bucket elsewhere.
#   2. Deny every request over plain HTTP, the same rule as the photos bucket policy.
# No other principal is allowed here.
data "aws_iam_policy_document" "photos_queue" {
  statement {
    sid       = "AllowS3PhotosBucketToSend"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.photos.arn]

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [var.photos_bucket_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
  }

  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["sqs:*"]
    resources = [aws_sqs_queue.photos.arn]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_sqs_queue_policy" "photos" {
  queue_url = aws_sqs_queue.photos.id
  policy    = data.aws_iam_policy_document.photos_queue.json
}

# ---------------------------------------------------------------- alarm

# Any message in the DLQ means a photo failed max_receive_count times and was never tagged.
# Maximum over 5 minutes catches a message that arrives and is redriven within the period.
# Idle SQS queues stop reporting metrics, so missing data is "not breaching".
resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name        = "${local.dlq_name}-not-empty"
  alarm_description = "A photo failed tagging ${var.max_receive_count} times and sits in ${local.dlq_name}. Inspect it, fix the cause, then redrive or delete. It is kept 14 days."

  namespace   = "AWS/SQS"
  metric_name = "ApproximateNumberOfMessagesVisible"
  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }

  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = var.alarm_actions
  ok_actions    = var.alarm_actions
}
