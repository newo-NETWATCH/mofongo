# Weekday stop and start (ADR 0004): the instance runs 8 hours a day, Monday to Friday, about 173
# hours a month instead of 730, so the Free plan credits last.
#
# Mechanism: two EventBridge Scheduler schedules that call the EC2 StartInstances and
# StopInstances APIs directly through the Scheduler "universal target". No Lambda, no code, no
# Systems Manager automation document. Both schedules assume one small role that may start and
# stop THIS instance only.
#
# Photos that arrive while the instance is stopped wait in the photo queue (7 days retention).
# The longest stop is Friday 16:00 to Monday 08:00, 64 hours. To run it outside the window, start
# it by hand: aws ec2 start-instances --instance-ids <id> --region us-east-2 --profile mofongo.
# A start does not re-run the bootstrap; systemd starts the worker.

locals {
  schedule_actions = {
    start = {
      api         = "startInstances"
      cron        = var.schedule_start_cron
      description = "Start the tagger on weekday mornings"
    }
    stop = {
      api         = "stopInstances"
      cron        = var.schedule_stop_cron
      description = "Stop the tagger on weekday afternoons"
    }
  }
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    sid     = "SchedulerAssumesRole"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  count = var.schedule_enabled ? 1 : 0

  name               = "${local.instance_name}-scheduler"
  description        = "Lets EventBridge Scheduler start and stop the ${local.instance_name} instance, and nothing else."
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid       = "StartStopTagger"
    actions   = ["ec2:StartInstances", "ec2:StopInstances"]
    resources = [aws_instance.tagger.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  count = var.schedule_enabled ? 1 : 0

  name   = "start-stop-tagger"
  role   = aws_iam_role.scheduler[0].id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "tagger" {
  for_each = var.schedule_enabled ? local.schedule_actions : {}

  name        = "${local.instance_name}-${each.key}"
  description = each.value.description
  group_name  = "default"

  schedule_expression          = each.value.cron
  schedule_expression_timezone = var.schedule_timezone
  state                        = "ENABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:${data.aws_partition.current.partition}:scheduler:::aws-sdk:ec2:${each.value.api}"
    role_arn = aws_iam_role.scheduler[0].arn
    input    = jsonencode({ InstanceIds = [aws_instance.tagger.id] })

    retry_policy {
      maximum_retry_attempts       = 3
      maximum_event_age_in_seconds = 3600
    }
  }

  depends_on = [aws_iam_role_policy.scheduler]
}
