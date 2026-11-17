# The API Lambda: one Python function that answers every route of the REST API.
#
# It runs OUTSIDE the VPC (no vpc_config). It reaches DynamoDB, SNS and S3 over their regional
# endpoints in us-east-2 with IAM auth. No reserved_concurrent_executions: the API stage
# throttle is the cap, and a reservation can fail on a new Free plan account.

data "aws_caller_identity" "current" {}

locals {
  function_name = "${var.name_prefix}-api"

  # Files the package must hold. A fresh clone that skipped scripts/build-api.ps1 fails at plan
  # with a clear message instead of deploying a function that cannot validate bodies.
  required_package_files = [
    "app.py",
    "schemas/requests/create-item.json",
    "schemas/requests/create-report.json",
    "schemas/shared/error.json",
  ]
  missing_package_files = [
    for f in local.required_package_files : f if !fileexists("${var.package_dir}/${f}")
  ]

  # Index ARNs by name. The role gets Query on exactly these, not on index/*.
  items_index_arns = [
    "${var.table_arns.items}/index/${var.index_names.items.listed_by_date}",
    "${var.table_arns.items}/index/${var.index_names.items.listed_by_category}",
  ]
  reports_index_arns = [
    "${var.table_arns.reports}/index/${var.index_names.reports.by_owner}",
  ]
}

# ---------------------------------------------------------------- package

# The zip holds backend/api/*.py, the pip dependencies, and the request/shared JSON schemas
# under schemas/. scripts/build-api.ps1 builds the folder; this only zips it.
data "archive_file" "api" {
  type        = "zip"
  source_dir  = var.package_dir
  output_path = "${var.package_dir}.zip"

  lifecycle {
    precondition {
      condition     = length(local.missing_package_files) == 0
      error_message = "The Lambda package at ${var.package_dir} is missing: ${join(", ", local.missing_package_files)}. Run scripts/build-api.ps1 first."
    }
  }
}

# ---------------------------------------------------------------- logs

# Terraform owns the log group, so the role needs no logs:CreateLogGroup.
resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
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

resource "aws_iam_role" "api" {
  name               = "${local.function_name}-lambda"
  description        = "Execution role of the ${local.function_name} Lambda. Least privilege, see docs/data-model.md section 5."
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# Every statement names the access pattern (AP) it serves in docs/data-model.md section 5.
# No AWS managed policy, no Resource "*", no Scan, no DeleteItem, no sns:Publish.
data "aws_iam_policy_document" "api" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.api.arn}:*"]
  }

  # AP3, AP4, AP7. BatchGetItem is AP8 (the items behind a report's matches).
  statement {
    sid       = "ItemsTable"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:BatchGetItem"]
    resources = [var.table_arns.items]
  }

  # AP1, AP2.
  statement {
    sid       = "ItemsBrowseIndexes"
    actions   = ["dynamodb:Query"]
    resources = local.items_index_arns
  }

  # AP9, AP11, AP12.
  statement {
    sid       = "ReportsTable"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [var.table_arns.reports]
  }

  # AP10. The API never reads OpenByCategory: that index belongs to the matcher.
  statement {
    sid       = "ReportsByOwnerIndex"
    actions   = ["dynamodb:Query"]
    resources = local.reports_index_arns
  }

  # AP13 only. The API never writes Matches (AP14 to AP16 are the matcher's).
  statement {
    sid       = "MatchesRead"
    actions   = ["dynamodb:Query"]
    resources = [var.table_arns.matches]
  }

  # AP19, AP20.
  statement {
    sid       = "UsersTable"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem"]
    resources = [var.table_arns.users]
  }

  # data-model 6.6: email subscriptions only. Publishing belongs to the matcher's role.
  statement {
    sid       = "SubscribeEmailToAlerts"
    actions   = ["sns:Subscribe"]
    resources = [var.alerts_topic_arn]

    condition {
      test     = "StringEquals"
      variable = "sns:Protocol"
      values   = ["email"]
    }
  }

  # GET /me/alerts and POST /me/alerts read a subscription back. The subscription ARN is the
  # topic ARN plus ":<id>". The topic ARN itself is listed too, in case IAM matches this action
  # against the topic.
  statement {
    sid       = "ReadAlertSubscriptionState"
    actions   = ["sns:GetSubscriptionAttributes"]
    resources = [var.alerts_topic_arn, "${var.alerts_topic_arn}:*"]
  }

  # Presigned photo upload (POST) and view (GET). A presigned URL is only as strong as the role
  # that signed it and is checked when it is used, so the role holds these two on photos/* only.
  statement {
    sid       = "PresignPhotoUpload"
    actions   = ["s3:PutObject"]
    resources = ["${var.photos_bucket_arn}/photos/*"]
  }

  statement {
    sid       = "PresignPhotoView"
    actions   = ["s3:GetObject"]
    resources = ["${var.photos_bucket_arn}/photos/*"]
  }
}

resource "aws_iam_role_policy" "api" {
  name   = "api"
  role   = aws_iam_role.api.id
  policy = data.aws_iam_policy_document.api.json
}

# ---------------------------------------------------------------- function

resource "aws_lambda_function" "api" {
  function_name = local.function_name
  description   = "Mofongo REST API handler (payload format 1.0)."
  role          = aws_iam_role.api.arn

  runtime       = var.runtime
  architectures = [var.architecture]
  handler       = "app.handler"
  memory_size   = var.memory_mb
  timeout       = var.timeout_seconds

  filename         = data.archive_file.api.output_path
  source_code_hash = data.archive_file.api.output_base64sha256

  # AWS_REGION is reserved: Lambda sets it and boto3 reads it. No secrets here, only names.
  environment {
    variables = {
      ITEMS_TABLE            = var.table_names.items
      REPORTS_TABLE          = var.table_names.reports
      MATCHES_TABLE          = var.table_names.matches
      USERS_TABLE            = var.table_names.users
      IDX_LISTED_BY_DATE     = var.index_names.items.listed_by_date
      IDX_LISTED_BY_CATEGORY = var.index_names.items.listed_by_category
      IDX_BY_OWNER           = var.index_names.reports.by_owner
      PHOTOS_BUCKET          = var.photos_bucket_name
      ALERTS_TOPIC_ARN       = var.alerts_topic_arn
      USER_POOL_ID           = var.cognito_user_pool_id
      APP_CLIENT_ID          = var.cognito_app_client_id
      CORS_ORIGIN            = var.cors_origin
      SCHEMA_DIR             = "/var/task/schemas"
      PRESIGN_TTL_SECONDS    = tostring(var.presign_ttl_seconds)
      PHOTO_MAX_BYTES        = tostring(var.photo_max_bytes)
      LOG_LEVEL              = var.log_level
    }
  }

  # X-Ray is off. Turning it on needs extra IAM.
  tracing_config {
    mode = "PassThrough"
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.api.name
  }

  depends_on = [
    aws_cloudwatch_log_group.api,
    aws_iam_role_policy.api,
  ]
}
