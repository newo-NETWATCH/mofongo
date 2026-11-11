# api module

API Gateway REST API (v1, regional) for the Mofongo API. The routes mirror `api/openapi.yaml`: 7 path items, 10 routes, all pointing at the one API Lambda.

What it makes:

- The REST API, its resources and the 10 methods. Every method uses the Cognito User Pools authorizer.
- An AWS_PROXY integration to the Lambda (payload format 1.0).
- Models and a body validator on `POST /items` and `POST /reports`. The schemas are read from `api/schemas/requests/`.
- A CORS preflight (OPTIONS, MOCK) per path item, and CORS headers on API Gateway's own error responses.
- A deployment and the `dev` stage, with an access log in CloudWatch and throttling.
- The permission that lets this API invoke the Lambda.
- The account-level API Gateway CloudWatch Logs role (one per account and Region; turn off with `manage_account_cloudwatch_role = false` if another stack owns it).

It does not make the Lambda or the Cognito pool. Pass them in.

## Inputs

| Name | Notes |
|---|---|
| `name_prefix`, `region`, `account_id` | Required. |
| `lambda_invoke_arn`, `lambda_function_name` | Required, from `api_lambda`. |
| `cognito_user_pool_arn` | Required, from `cognito`. |
| `cors_origin` | One exact origin. Default `http://localhost:5173`. No wildcard. |
| `throttle_rate`, `throttle_burst` | Stage default. 20 and 10. |
| `write_throttle_rate`, `write_throttle_burst` | `POST /items` and `POST /me/alerts`. 1 and 5. |
| `stage_name`, `integration_timeout_ms`, `log_retention_days`, `schema_dir` | Optional. |

## Outputs

`rest_api_id`, `stage_arn` (use it for the WAF association), `stage_name`, `execution_arn`, `invoke_url`, `authorizer_id`, `access_log_group_name`.

## Notes

- The invoke URL ends in `/dev`. Add the route after it.
- With a Lambda proxy integration, API Gateway does not add CORS headers to the Lambda's answers. The handler must send `Access-Control-Allow-Origin` on every response.
- The gateway validates the body only when `Content-Type` is `application/json`. The Lambda checks the body again for every other content type.
- The Cognito authorizer rejects access tokens when no scopes are set, but the Lambda still checks `token_use = id`.
- Adding a route means editing `local.routes` (and a resource if the path is new) in `main.tf`.
