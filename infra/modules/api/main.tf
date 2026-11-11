# REST API (API Gateway v1) for the Mofongo API, in the selected Region.
#
# The routes mirror api/openapi.yaml: 7 path items, 10 routes. If you add or
# change a route there, change `local.routes` and the resources below in the
# same commit.
#
# Every route needs a signed-in user (Cognito User Pools authorizer). The only
# unauthenticated methods are the CORS OPTIONS preflights in cors.tf, which a
# browser sends without a token.

locals {
  schema_dir = coalesce(var.schema_dir, "${path.module}/../../../api/schemas/requests")

  # Request bodies the gateway validates before the Lambda runs. The Lambda
  # checks them again (defense in depth).
  models = {
    create_item   = { name = "CreateItem", file = "create-item.json" }
    create_report = { name = "CreateReport", file = "create-report.json" }
  }

  # Resource id by path key, used to attach methods.
  resource_ids = {
    items         = aws_api_gateway_resource.items.id
    item          = aws_api_gateway_resource.item.id
    item_returned = aws_api_gateway_resource.item_returned.id
    reports       = aws_api_gateway_resource.reports.id
    report        = aws_api_gateway_resource.report.id
    report_closed = aws_api_gateway_resource.report_closed.id
    me_alerts     = aws_api_gateway_resource.me_alerts.id
  }

  # One entry per route. `model` names the body schema, or null for no body.
  routes = {
    "GET /items"                      = { path = "items", method = "GET", model = null }
    "POST /items"                     = { path = "items", method = "POST", model = "create_item" }
    "GET /items/{itemId}"             = { path = "item", method = "GET", model = null }
    "POST /items/{itemId}/returned"   = { path = "item_returned", method = "POST", model = null }
    "GET /reports"                    = { path = "reports", method = "GET", model = null }
    "POST /reports"                   = { path = "reports", method = "POST", model = "create_report" }
    "GET /reports/{reportId}"         = { path = "report", method = "GET", model = null }
    "POST /reports/{reportId}/closed" = { path = "report_closed", method = "POST", model = null }
    "GET /me/alerts"                  = { path = "me_alerts", method = "GET", model = null }
    "POST /me/alerts"                 = { path = "me_alerts", method = "POST", model = null }
  }

  # Methods per path item, for the CORS Allow-Methods header.
  path_methods = {
    for path in distinct([for r in local.routes : r.path]) :
    path => [for r in local.routes : r.method if r.path == path]
  }
}

resource "aws_api_gateway_rest_api" "this" {
  name        = "${var.name_prefix}-api"
  description = "Mofongo lost-and-found API. Routes mirror api/openapi.yaml."

  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

# Path tree: /items, /items/{itemId}, /items/{itemId}/returned, /reports,
# /reports/{reportId}, /reports/{reportId}/closed, /me, /me/alerts.
resource "aws_api_gateway_resource" "items" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "items"
}

resource "aws_api_gateway_resource" "item" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.items.id
  path_part   = "{itemId}"
}

resource "aws_api_gateway_resource" "item_returned" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.item.id
  path_part   = "returned"
}

resource "aws_api_gateway_resource" "reports" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "reports"
}

resource "aws_api_gateway_resource" "report" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.reports.id
  path_part   = "{reportId}"
}

resource "aws_api_gateway_resource" "report_closed" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.report.id
  path_part   = "closed"
}

# /me has no methods of its own, so it gets no CORS preflight.
resource "aws_api_gateway_resource" "me" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_rest_api.this.root_resource_id
  path_part   = "me"
}

resource "aws_api_gateway_resource" "me_alerts" {
  rest_api_id = aws_api_gateway_rest_api.this.id
  parent_id   = aws_api_gateway_resource.me.id
  path_part   = "alerts"
}

# Cognito User Pools authorizer. With no scopes on the methods it accepts ID
# tokens and rejects access tokens. The Lambda still checks token_use = id.
resource "aws_api_gateway_authorizer" "cognito" {
  name            = "cognito-id-token"
  rest_api_id     = aws_api_gateway_rest_api.this.id
  type            = "COGNITO_USER_POOLS"
  provider_arns   = [var.cognito_user_pool_arn]
  identity_source = "method.request.header.Authorization"
}

# Body schemas, loaded from the same files the Lambda validates with.
resource "aws_api_gateway_model" "this" {
  for_each = local.models

  rest_api_id  = aws_api_gateway_rest_api.this.id
  name         = each.value.name
  description  = "Request body schema from api/schemas/requests/${each.value.file}."
  content_type = "application/json"
  schema       = file("${local.schema_dir}/${each.value.file}")
}

# Checks the body only. Query and path values are checked by the Lambda.
resource "aws_api_gateway_request_validator" "body" {
  name                        = "validate-body"
  rest_api_id                 = aws_api_gateway_rest_api.this.id
  validate_request_body       = true
  validate_request_parameters = false
}

resource "aws_api_gateway_method" "this" {
  for_each = local.routes

  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = local.resource_ids[each.value.path]
  http_method   = each.value.method
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id

  request_validator_id = each.value.model == null ? null : aws_api_gateway_request_validator.body.id
  request_models = each.value.model == null ? null : {
    "application/json" = aws_api_gateway_model.this[each.value.model].name
  }
}

resource "aws_api_gateway_integration" "this" {
  for_each = local.routes

  rest_api_id             = aws_api_gateway_rest_api.this.id
  resource_id             = local.resource_ids[each.value.path]
  http_method             = aws_api_gateway_method.this[each.key].http_method
  type                    = "AWS_PROXY"
  integration_http_method = "POST"
  uri                     = var.lambda_invoke_arn
  timeout_milliseconds    = var.integration_timeout_ms
}

# Only this API, only its stage, may invoke the Lambda.
resource "aws_lambda_permission" "invoke" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.this.execution_arn}/${var.stage_name}/*/*"
}
