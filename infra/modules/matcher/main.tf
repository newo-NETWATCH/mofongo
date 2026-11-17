# The matcher: one Python function that DynamoDB Streams starts. It pairs found items with open
# lost reports and publishes one email message per new pair. Spec: docs/data-model.md section 6.
#
# It runs OUTSIDE the VPC (no vpc_config). It reaches DynamoDB, SNS and SQS over their regional
# endpoints in us-east-2 with IAM auth. No reserved_concurrent_executions: a reservation can fail
# on a new Free plan account, and the stream shards already cap concurrency (one batch per shard).
#
# This module takes the tables, indexes, streams and topic as inputs. It creates none of them.

data "aws_caller_identity" "current" {}

locals {
  function_name = "${var.name_prefix}-matcher"

  # Files the package must hold. A fresh clone that skipped the build step fails at plan with a
  # clear message instead of deploying a function whose handler cannot be imported.
  handler_module = split(".", var.handler)[0]
  required_package_files = [
    "${local.handler_module}.py",
  ]
  missing_package_files = [
    for f in local.required_package_files : f if !fileexists("${var.package_dir}/${f}")
  ]

  # Index ARNs by name. The role gets Query on exactly these two, not on index/*.
  listed_by_category_arn = "${var.table_arns.items}/index/${var.index_names.items.listed_by_category}"
  open_by_category_arn   = "${var.table_arns.reports}/index/${var.index_names.reports.open_by_category}"

  # Settings that data-model 6.2 gives for BOTH mappings.
  mapping = {
    starting_position                  = "LATEST"
    batch_size                         = 10
    maximum_batching_window_in_seconds = 0
    maximum_retry_attempts             = 3
    maximum_record_age_in_seconds      = 21600 # 6 hours
  }

  # data-model 6.2, Items filter: a LISTED item whose tagStatus went from PENDING to TAGGED.
  # An OldImage only exists on a change, so this can only match a MODIFY. NewImage and OldImage
  # sit inside ONE "dynamodb" object, because repeating the "dynamodb" key loses the AND.
  items_filter = {
    dynamodb = {
      NewImage = {
        status    = { S = ["LISTED"] }
        tagStatus = { S = ["TAGGED"] }
      }
      OldImage = {
        tagStatus = { S = ["PENDING"] }
      }
    }
  }

  # data-model 6.2, Reports filter: a newly INSERTed OPEN report. A new report has no OldImage,
  # so exists:false on the leaf OldImage.reportId.S matches only an INSERT. If the first-deploy
  # test in 6.2 fails, drop the OldImage part and keep NewImage.status = OPEN.
  reports_filter = {
    dynamodb = {
      NewImage = {
        status = { S = ["OPEN"] }
      }
      OldImage = {
        reportId = { S = [{ exists = false }] }
      }
    }
  }
}

# ---------------------------------------------------------------- package

# The zip holds backend/matcher/*.py (and dependencies, if any). boto3 is not bundled: the
# python3.13 Lambda runtime provides it. A build script fills package_dir; this only zips it.
data "archive_file" "matcher" {
  type        = "zip"
  source_dir  = var.package_dir
  output_path = "${var.package_dir}.zip"

  lifecycle {
    precondition {
      condition     = length(local.missing_package_files) == 0
      error_message = "The Lambda package at ${var.package_dir} is missing: ${join(", ", local.missing_package_files)}. Build the matcher package first (see this module's README)."
    }
  }
}

# ---------------------------------------------------------------- logs

# Terraform owns the log group, so the role needs no logs:CreateLogGroup.
resource "aws_cloudwatch_log_group" "matcher" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

# ---------------------------------------------------------------- failure queue

# data-model 6.2: records the mappings give up on leave a note here (shard and sequence numbers,
# not the record itself). Alarm on this queue being non-empty. Standard queue, encrypted at rest
# with the SQS-owned key.
resource "aws_sqs_queue" "failed" {
  name                      = "${local.function_name}-failed"
  sqs_managed_sse_enabled   = true
  message_retention_seconds = 1209600 # 14 days, the SQS maximum
}

# ---------------------------------------------------------------- role

data "aws_iam_policy_document" "assume" {
  statement {
    sid     = "LambdaAssumesRole"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    # Confused deputy protection: only Lambda in this project may assume the role.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "matcher" {
  name               = "${local.function_name}-lambda"
  description        = "Execution role of the ${local.function_name} Lambda. Least privilege, see docs/data-model.md sections 5 and 6."
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# Every statement names the access pattern (AP) it serves in docs/data-model.md section 5.
# No AWS managed policy, no Resource "*", no Scan, no Users table, no sns:Subscribe.
data "aws_iam_policy_document" "matcher" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.matcher.arn}:*"]
  }

  # What the event source mappings need to poll the two streams, on these two ARNs only. Lambda
  # polls with this role. ListStreams is included because Lambda's own managed policy has it; it
  # is scoped to the stream ARNs here, not "*".
  statement {
    sid     = "ReadItemsAndReportsStreams"
    actions = ["dynamodb:GetRecords", "dynamodb:GetShardIterator", "dynamodb:DescribeStream", "dynamodb:ListStreams"]
    resources = [
      var.stream_arns.items,
      var.stream_arns.reports,
    ]
  }

  # AP3: re-read a PENDING item (6.5). Reports GetItem is the optional re-read of 6.8.
  statement {
    sid     = "ReadItemsAndReports"
    actions = ["dynamodb:GetItem"]
    resources = [
      var.table_arns.items,
      var.table_arns.reports,
    ]
  }

  # AP17 and AP18. Nothing else is queried: the browse and by-owner indexes are the API's.
  statement {
    sid     = "QueryCandidateIndexes"
    actions = ["dynamodb:Query"]
    resources = [
      local.open_by_category_arn,
      local.listed_by_category_arn,
    ]
  }

  # AP14 (PutItem, conditional), AP15 (UpdateItem), AP16 (DeleteItem, conditional). The matcher
  # is the only writer of Matches; it never reads it back with Query or Scan.
  statement {
    sid       = "RecordMatches"
    actions   = ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
    resources = [var.table_arns.matches]
  }

  # data-model 6.7: the one message per new pair. This is the only topic the role can publish to.
  statement {
    sid       = "PublishMatchAlert"
    actions   = ["sns:Publish"]
    resources = [var.alerts_topic_arn]
  }

  # data-model 6.2: the mappings send a note about a given-up record to the failure queue with
  # this role.
  statement {
    sid       = "NoteFailedRecords"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.failed.arn]
  }
}

resource "aws_iam_role_policy" "matcher" {
  name   = "matcher"
  role   = aws_iam_role.matcher.id
  policy = data.aws_iam_policy_document.matcher.json
}

# ---------------------------------------------------------------- function

resource "aws_lambda_function" "matcher" {
  function_name = local.function_name
  description   = "Mofongo matcher: pairs tagged items with open reports and emails the owner (data-model section 6)."
  role          = aws_iam_role.matcher.arn

  runtime       = var.runtime
  architectures = [var.architecture]
  handler       = var.handler
  memory_size   = var.memory_mb
  timeout       = var.timeout_seconds

  filename         = data.archive_file.matcher.output_path
  source_code_hash = data.archive_file.matcher.output_base64sha256

  # AWS_REGION is reserved: Lambda sets it and boto3 reads it. No secrets here, only names.
  environment {
    variables = {
      ITEMS_TABLE            = var.table_names.items
      REPORTS_TABLE          = var.table_names.reports
      MATCHES_TABLE          = var.table_names.matches
      IDX_LISTED_BY_CATEGORY = var.index_names.items.listed_by_category
      IDX_OPEN_BY_CATEGORY   = var.index_names.reports.open_by_category
      ALERTS_TOPIC_ARN       = var.alerts_topic_arn
      SITE_URL               = var.site_url
      MATCH_THRESHOLD        = tostring(var.match_threshold)
      LOG_LEVEL              = var.log_level
    }
  }

  # X-Ray is off. Turning it on needs extra IAM.
  tracing_config {
    mode = "PassThrough"
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.matcher.name
  }

  depends_on = [
    aws_cloudwatch_log_group.matcher,
    aws_iam_role_policy.matcher,
  ]
}

# ---------------------------------------------------------------- event source mappings

# Items stream: runs when a listed item gets its tags (direction A, data-model 6.4).
resource "aws_lambda_event_source_mapping" "items" {
  function_name    = aws_lambda_function.matcher.arn
  event_source_arn = var.stream_arns.items

  starting_position                  = local.mapping.starting_position
  batch_size                         = local.mapping.batch_size
  maximum_batching_window_in_seconds = local.mapping.maximum_batching_window_in_seconds
  maximum_retry_attempts             = local.mapping.maximum_retry_attempts
  maximum_record_age_in_seconds      = local.mapping.maximum_record_age_in_seconds
  bisect_batch_on_function_error     = true
  function_response_types            = ["ReportBatchItemFailures"]

  filter_criteria {
    filter {
      pattern = jsonencode(local.items_filter)
    }
  }

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.failed.arn
    }
  }

  # The role must be able to read the stream, and send to the queue, before Lambda validates it.
  depends_on = [aws_iam_role_policy.matcher]
}

# Reports stream: runs when a report is filed (direction B, data-model 6.5).
resource "aws_lambda_event_source_mapping" "reports" {
  function_name    = aws_lambda_function.matcher.arn
  event_source_arn = var.stream_arns.reports

  starting_position                  = local.mapping.starting_position
  batch_size                         = local.mapping.batch_size
  maximum_batching_window_in_seconds = local.mapping.maximum_batching_window_in_seconds
  maximum_retry_attempts             = local.mapping.maximum_retry_attempts
  maximum_record_age_in_seconds      = local.mapping.maximum_record_age_in_seconds
  bisect_batch_on_function_error     = true
  function_response_types            = ["ReportBatchItemFailures"]

  filter_criteria {
    filter {
      pattern = jsonencode(local.reports_filter)
    }
  }

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.failed.arn
    }
  }

  depends_on = [aws_iam_role_policy.matcher]
}
