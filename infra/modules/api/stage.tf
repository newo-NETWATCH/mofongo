# Deployment, the "dev" stage, access logging and throttling.

data "aws_iam_policy_document" "apigw_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["apigateway.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
  }
}

# API Gateway needs one CloudWatch Logs role per account and Region before any
# stage can write an access log. It is one setting for the whole Region, so set
# manage_account_cloudwatch_role = false if another stack already owns it.
resource "aws_iam_role" "apigw_cloudwatch" {
  count = var.manage_account_cloudwatch_role ? 1 : 0

  name               = "${var.name_prefix}-apigw-cloudwatch"
  assume_role_policy = data.aws_iam_policy_document.apigw_trust.json
}

resource "aws_iam_role_policy_attachment" "apigw_cloudwatch" {
  count = var.manage_account_cloudwatch_role ? 1 : 0

  role       = aws_iam_role.apigw_cloudwatch[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

resource "aws_api_gateway_account" "this" {
  count = var.manage_account_cloudwatch_role ? 1 : 0

  cloudwatch_role_arn = aws_iam_role.apigw_cloudwatch[0].arn

  depends_on = [aws_iam_role_policy_attachment.apigw_cloudwatch]
}

resource "aws_cloudwatch_log_group" "access" {
  name              = "/aws/apigateway/${var.name_prefix}-api-access"
  retention_in_days = var.log_retention_days
}

resource "aws_api_gateway_deployment" "this" {
  rest_api_id = aws_api_gateway_rest_api.this.id

  # A new deployment whenever any part of the API definition changes.
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.items,
      aws_api_gateway_resource.item,
      aws_api_gateway_resource.item_returned,
      aws_api_gateway_resource.reports,
      aws_api_gateway_resource.report,
      aws_api_gateway_resource.report_closed,
      aws_api_gateway_resource.me,
      aws_api_gateway_resource.me_alerts,
      aws_api_gateway_authorizer.cognito,
      aws_api_gateway_model.this,
      aws_api_gateway_request_validator.body,
      aws_api_gateway_method.this,
      aws_api_gateway_integration.this,
      aws_api_gateway_method.options,
      aws_api_gateway_integration.options,
      aws_api_gateway_method_response.options,
      aws_api_gateway_integration_response.options,
      aws_api_gateway_gateway_response.default_4xx,
      aws_api_gateway_gateway_response.default_5xx,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "this" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  deployment_id = aws_api_gateway_deployment.this.id
  stage_name    = var.stage_name

  xray_tracing_enabled = false

  # Authorization header, query strings and bodies are never logged: they hold
  # tokens and personal data.
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.access.arn
    format = jsonencode({
      requestId               = "$context.requestId"
      ip                      = "$context.identity.sourceIp"
      requestTime             = "$context.requestTime"
      httpMethod              = "$context.httpMethod"
      resourcePath            = "$context.resourcePath"
      status                  = "$context.status"
      protocol                = "$context.protocol"
      responseLength          = "$context.responseLength"
      responseLatency         = "$context.responseLatency"
      integrationStatus       = "$context.integrationStatus"
      integrationErrorMessage = "$context.integrationErrorMessage"
      authorizerError         = "$context.authorizer.error"
      wafResponseCode         = "$context.wafResponseCode"
    })
  }

  depends_on = [aws_api_gateway_account.this]
}

# Throttling. Limits are shared by all callers together (no per-user limits
# without usage plans and keys). Logging stays OFF here: execution logs would
# create a log group that Terraform does not manage, and the access log above
# is enough. Every override restates the other settings, because a path-level
# entry does not inherit them from "*/*".
locals {
  throttle_settings = merge(
    {
      default = {
        path  = "*/*"
        rate  = var.throttle_rate
        burst = var.throttle_burst
      }
    },
    {
      items_post = {
        path  = "items/POST"
        rate  = var.write_throttle_rate
        burst = var.write_throttle_burst
      }
      me_alerts_post = {
        path  = "me/alerts/POST"
        rate  = var.write_throttle_rate
        burst = var.write_throttle_burst
      }
    }
  )
}

resource "aws_api_gateway_method_settings" "this" {
  for_each = local.throttle_settings

  rest_api_id = aws_api_gateway_rest_api.this.id
  stage_name  = aws_api_gateway_stage.this.stage_name
  method_path = each.value.path

  settings {
    metrics_enabled        = true
    logging_level          = "OFF"
    data_trace_enabled     = false
    throttling_rate_limit  = each.value.rate
    throttling_burst_limit = each.value.burst
  }

  # Method-level entries are applied after the stage default, in a fixed order.
  depends_on = [aws_api_gateway_stage.this]
}
