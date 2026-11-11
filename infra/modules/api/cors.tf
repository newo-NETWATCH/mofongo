# CORS for the browser app.
#
# Preflight (OPTIONS) is answered by API Gateway with a MOCK integration, so it
# never reaches the Lambda. A preflight carries no token, so these OPTIONS
# methods are the one place authorization = "NONE" is correct. They return only
# static headers and no data.
#
# The real responses (200, 201, 4xx from the Lambda) still need
# Access-Control-Allow-Origin. With a Lambda proxy integration API Gateway does
# not add it, so the handler must send it on every response.

resource "aws_api_gateway_method" "options" {
  for_each = local.path_methods

  rest_api_id   = aws_api_gateway_rest_api.this.id
  resource_id   = local.resource_ids[each.key]
  http_method   = "OPTIONS"
  authorization = "NONE" # tfsec:ignore:aws-api-gateway-no-public-access
}

resource "aws_api_gateway_integration" "options" {
  for_each = local.path_methods

  rest_api_id = aws_api_gateway_rest_api.this.id
  resource_id = local.resource_ids[each.key]
  http_method = aws_api_gateway_method.options[each.key].http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = jsonencode({ statusCode = 200 })
  }
}

resource "aws_api_gateway_method_response" "options" {
  for_each = local.path_methods

  rest_api_id = aws_api_gateway_rest_api.this.id
  resource_id = local.resource_ids[each.key]
  http_method = aws_api_gateway_method.options[each.key].http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin"  = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Max-Age"       = true
  }
}

resource "aws_api_gateway_integration_response" "options" {
  for_each = local.path_methods

  rest_api_id = aws_api_gateway_rest_api.this.id
  resource_id = local.resource_ids[each.key]
  http_method = aws_api_gateway_method.options[each.key].http_method
  status_code = aws_api_gateway_method_response.options[each.key].status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin"  = "'${var.cors_origin}'"
    "method.response.header.Access-Control-Allow-Methods" = "'${join(",", concat(each.value, ["OPTIONS"]))}'"
    "method.response.header.Access-Control-Allow-Headers" = "'Authorization,Content-Type'"
    "method.response.header.Access-Control-Max-Age"       = "'300'"
  }

  depends_on = [aws_api_gateway_integration.options]
}

# Errors that API Gateway makes itself (401 from the authorizer, 400 from body
# validation, 429 throttling, 5xx) get the origin header too. Without it the
# browser hides the status and the app sees only a CORS failure.
resource "aws_api_gateway_gateway_response" "default_4xx" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  response_type = "DEFAULT_4XX"

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin" = "'${var.cors_origin}'"
  }
}

resource "aws_api_gateway_gateway_response" "default_5xx" {
  rest_api_id   = aws_api_gateway_rest_api.this.id
  response_type = "DEFAULT_5XX"

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin" = "'${var.cors_origin}'"
  }
}
