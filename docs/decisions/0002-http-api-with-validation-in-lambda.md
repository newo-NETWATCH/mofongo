# 0002. HTTP API with validation in the Lambda

Date: 2026-10-21
Status: Accepted

## Context

- The web app calls ten endpoints: the eight in Part 3 of `docs/plan.md` and two added in `docs/data-model.md` section 1. Every one needs a signed-in user.
- The web app sends the Cognito ID token. The API Lambda needs its `sub`, `email` and `email_verified` claims to subscribe the owner's email (see 0003).
- API Gateway has several API types. They differ in price and in features.
- Some request bodies, such as posting an item or filing a report, must be checked before the Lambda uses them.

## Decision

- Use an API Gateway HTTP API in us-east-2 with one JWT authorizer. The issuer is the Cognito user pool. The audience is the app client ID.
- API Gateway checks the token before the Lambda runs. It passes the claims to the Lambda in `event.requestContext.authorizer.jwt.claims`.
- The API Lambda checks that the token's `token_use` claim is `id` on every route and answers HTTP 401 if not (see `docs/data-model.md` section 3).
- The API Lambda (Python 3.13) checks each request body against a JSON Schema file in `api/schemas/`, one file per body. A body that fails gets HTTP 400.
- Write the schemas in the draft-4 subset. API Gateway REST APIs use draft 4 for their models, so the same files could move to a REST API later.

How the options compare:

| | HTTP API | REST API | Lambda function URL |
|---|---|---|---|
| Price per million requests (first tier, us-east-2) | about $1.00 | about $3.50 | no charge for the URL, normal Lambda pricing |
| Request validation | No | Yes | No |
| API keys, usage plans, per-client limits | No | Yes | No |
| AWS WAF directly on the API | No | Yes | Not listed |
| Checks Cognito or JWT tokens | Yes, JWT authorizer | Yes, Cognito authorizer | No. Only IAM sign-in or none |

## Consequences

Easier:
- The HTTP API is the cheapest API Gateway type, and the token check is built in. There is no authorizer code to write.
- A bad or missing token never reaches the Lambda.
- The schema files are plain files. They can be tested on a laptop with no AWS.

Harder or riskier:
- The Lambda must check every body on every route. A route that forgets the check is a bug the gateway will not catch. Use one shared helper and one test per schema.
- A bad body still starts the Lambda, so it costs a little compute time.
- There are no API keys and no per-client limits. The gateway does not stop one signed-in user from sending many requests.
- There is no AWS WAF in front of the API. The project rules also rule out WAF on CloudFront, because that needs us-east-1. This is a security gap to accept for now.
- The JWT authorizer cannot tell an ID token from an access token. AWS suggests requiring scopes unless you need ID tokens, but this app needs the ID token for the email claims. Setting the audience to this app client is not enough: a Cognito access token has no `aud`, so API Gateway checks its `client_id`, and an access token from the same client passes. The API Lambda therefore rejects any token whose `token_use` claim is not `id`.
- Draft 4 has fewer keywords than later drafts. There is no `const` and no `if/then/else`. `exclusiveMinimum` and `exclusiveMaximum` are true/false flags that go with `minimum` and `maximum`, not numbers.
- Moving to a REST API later is possible, but it costs more per request and the authorizer type changes.

## Alternatives considered

| Option | Why not |
|---|---|
| REST API with request validators | The gateway rejects bad bodies before the Lambda runs, and it has API keys and WAF. It costs about 3.5 times as much per request. This app does not need those features yet. The draft-4 schemas keep this option open. |
| Lambda function URLs | No extra charge, but they offer only IAM sign-in or none. The Lambda would have to check Cognito tokens itself, and there is no validation. AWS recommends function URLs for simple apps and prototypes, and API Gateway for production apps. |

## Sources

Checked on 2026-10-21.

- HTTP API vs REST API: https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html
- API Gateway prices: https://aws.amazon.com/api-gateway/pricing/
- JWT authorizers: https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html
- Function URL or API Gateway: https://docs.aws.amazon.com/lambda/latest/dg/furls-http-invoke-decision.html
- Function URL auth types: https://docs.aws.amazon.com/lambda/latest/api/API_FunctionUrlConfig.html
- REST API models use draft 4: https://docs.aws.amazon.com/apigateway/latest/developerguide/models-mappings-models.html
- Draft-6 changes (`const`, `exclusiveMinimum`): https://json-schema.org/draft-06/json-schema-release-notes
- Draft-7 changes (`if/then/else`): https://json-schema.org/draft-07/json-schema-release-notes
