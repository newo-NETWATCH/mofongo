# 0006. REST API for gateway-side validation and WAF

Date: 2026-11-11
Status: Accepted. Supersedes 0002.

## Context

- 0002 chose an API Gateway HTTP API with a Cognito JWT authorizer, and put body validation in the Lambda. It listed the REST API as the option that "keeps this option open" and said the draft-4 schemas were written so they could move.
- That fallback is now being used. Owen chose a REST API (v1) on 2026-11-11. The reasons:
  - **Gateway-side request validation.** A bad body is rejected before the Lambda starts. 0002 listed "a route that forgets the check" as a risk the gateway would not catch.
  - **AWS WAF on the API.** 0005 dropped the article's WAF control because it does not attach to an HTTP API. A REST API stage is a supported WAF resource, and a REGIONAL web ACL is created in us-east-2, so it fits the project's Region rule. (WAF on CloudFront still needs us-east-1 and stays ruled out.)
  - **Usage plans.** 0002 accepted that the gateway cannot limit one client. REST APIs have usage plans, plus per-stage and per-method throttling.
- The facts that did not change: ten routes, every one needs a signed-in user, the web app sends the Cognito ID token, and the Lambda needs the `sub`, `email` and `email_verified` claims (see 0003). The Lambdas stay outside the VPC (0004, 0005).
- The two request bodies are in `api/schemas/requests/create-item.json` and `create-report.json`. Both are standalone draft-4 files with no `$ref`, so they load as API Gateway models and in the Lambda without a resolver.

## Decision

- Use an API Gateway REST API (REGIONAL endpoint) in us-east-2, with one stage, `dev`. It replaces the HTTP API in 0002.
- **Authorizer.** A Cognito User Pools authorizer replaces the JWT authorizer. It is set on all ten methods. The token comes from the `Authorization` header. No authorization scopes are configured, so API Gateway treats the token as an ID token, and an access token is refused at the gateway. The claims reach the Lambda in `event.requestContext.authorizer.claims`.
- **Validation.** The two request schemas become API Gateway models. One request validator (body only) is attached to `POST /items` and `POST /reports`. The gateway answers 400 for a bad body. Query-string and path parameters are still checked in the Lambda.
- **WAF.** One REGIONAL web ACL in us-east-2, associated with the `dev` stage:
  - default action allow;
  - the `AWSManagedRulesCommonRuleSet` managed rule group (no overrides);
  - a rate-based rule: 2000 requests per 5 minutes per source IP.
- **Throttling and usage plans.** Stage-level method settings cap the request rate (about 20 per second, burst 10), tighter on the POST routes. Usage plans are now possible, but see "Harder or riskier" for what they do and do not cover. The first build relies on the method settings.
- **Lambda.** It moves to payload format 1.0: `httpMethod`, `resource`, `pathParameters`, `queryStringParameters`, case-sensitive `headers`, a string `body` that may be base64, and claims at `requestContext.authorizer.claims`.
- **Kept in the Lambda as defense in depth.** None of these is removed, because the Lambda is the last check before data is written:
  - reject `token_use` other than `id` with 401, and reject a missing `sub` with 401;
  - reject a body over 32768 bytes after base64 decoding with 413;
  - validate create-item and create-report with `jsonschema` `Draft4Validator` against the same files in `api/schemas/requests/`;
  - answer errors in the shape of `api/schemas/shared/error.json` (`message`, `details[]`);
  - take `finderId`, `ownerId` and `userId` only from the `sub` claim (`docs/data-model.md` section 3).
- **CORS.** Each resource gets an OPTIONS method with a MOCK integration. The allowed origin is a variable, default `http://localhost:5173`. The Lambda also sends the CORS headers on its own responses, because the OPTIONS mock covers only the preflight.
- **Cost.** A REST API costs about $3.50 per million requests (first tier, us-east-2), against about $1.00 for an HTTP API. At this app's volume the difference is cents a month. WAF adds about $5 a month for the web ACL, $1 for each rule, and $0.60 per million requests inspected. That is the larger cost, and it is still small next to the NAT or endpoints in 0005. Prices are approximate and were not re-checked live.

Trust boundaries (what each control does after this change):

| Boundary | Enforced by | Notes |
|---|---|---|
| Internet to the API | WAF common rules and rate rule, then stage throttling, then the Cognito authorizer | Before this record only throttling and the authorizer existed. |
| API Gateway to the Lambda | Gateway validator (two POST bodies), then the Lambda's own checks | The Lambda still trusts nothing the gateway did. The check is cheap and the Lambda can be invoked by mistake from another route. |
| Token to identity | Authorizer verifies the signature, expiry and issuer. The Lambda checks `token_use` and reads `sub` | A route or method added without the authorizer has no claims, and the Lambda answers 401. That fails closed. |
| Lambda to DynamoDB and S3 | IAM role per Lambda, limited to its tables, indexes and bucket prefix | Unchanged from 0004. |
| Browser to the photos bucket | Presigned PUT URL, private bucket, CORS limited to the app origin | The URL is a bearer credential. Keep it short-lived and tied to the user's key prefix. |

## Consequences

Easier:
- A malformed create-item or create-report body never starts the Lambda, so it costs no compute, and a forgotten check in one handler no longer lets junk past the gateway for those two routes.
- The API has a managed-rules layer against common web attacks and an IP rate rule. The residual risk "no WAF" in 0005 is closed for the API.
- The Cognito authorizer refuses access tokens at the gateway when no scopes are set, so the ID/access confusion in 0002 is blocked twice, not once.
- The same schema files serve the gateway and the Lambda. One change to a file updates both.
- Usage plans, API keys and per-method throttles are available if a client ever needs its own limit.

Harder or riskier:
- Costs about 3.5 times as much per request, plus WAF charges (see Decision). Both are small here.
- More Terraform: resources, methods, models, a validator, an OPTIONS mock per resource, a deployment and stage, access logs, and the WAF module. A REST API needs an `aws_api_gateway_deployment` that is re-created when any method or integration changes, or the change never goes live. Use a `triggers` hash and `create_before_destroy`.
- The gateway validates the body only against the model. A model checks shape, not meaning, and it checks only these two routes. Authorization (who owns this item) still lives only in the Lambda and is not made safer by this change.
- Two validators must agree. If a model and the Lambda drift apart, one rejects what the other accepts. Both read the same files, and one test per schema should run the files through `Draft4Validator`.
- Usage plans limit by API key, not by user. A key shipped in a browser app is public, so it identifies the app, not a person. Plans give a shared quota and throttle for the app, not a per-user limit. The gap 0002 accepted (one signed-in user can send many requests) is narrowed by the WAF rate rule per IP and by the method throttle, and is not fully closed. A per-user limit would need the `sub` counted in the Lambda or in DynamoDB. Requiring a key also adds an `x-api-key` header to every call and to CORS.
- The WAF common rule set includes a body size rule that blocks bodies over 8 KB by default. The Lambda limit of 32 KiB is therefore not reachable through the WAF for the body rule. Photos go straight to S3 and the JSON bodies are small, so this is expected to be fine. Check the create-item and create-report maximum sizes against it before the first deploy, and watch the WAF count and block metrics for false positives.
- The WAF rate rule counts by source IP. Many users behind one campus or office address share one limit, and an attacker with many addresses is not slowed by it. The 2000-per-5-minutes figure is a first guess to tune from the logs.
- WAF and API access logs hold IP addresses and request paths. Set a short retention on the log groups, and keep tokens and bodies out of them. Do not log the `Authorization` header.
- The REST API default endpoint is public and WAF applies only through the stage. Leave the default `execute-api` endpoint on, since there is no custom domain, and treat the stage URL as the only entry point.
- The OPTIONS mock answers without any authorizer, by design. It must return only CORS headers and no data.
- The Lambda now reads event format 1.0. Handler code, test events and `api/README.md` and `docs/data-model.md` wording written for format 2.0 (`requestContext.authorizer.jwt.claims`, `rawPath`) need updating.
- Switching later back to an HTTP API would mean redoing the integration, authorizer and event parsing again.

## Alternatives considered

| Option | Why not |
|---|---|
| Keep the HTTP API from 0002 | No gateway validation and no WAF. The supervisor's three-tier reference had WAF as a control, and the API was the one public entry point without it. |
| HTTP API behind CloudFront with WAF | WAF on CloudFront needs us-east-1, which the project rules forbid. It would also add a distribution for the API. |
| Lambda function URLs | Still no validation, no WAF and no Cognito check. Same objections as in 0002. |
| REST API with the WAF added later | Possible, since the stage ARN is an output. Not chosen because adding it now costs a small module and the rule set is cheap. |
| Per-user limit now (count `sub` in DynamoDB) | Extra writes on every request and more code. Revisit if the WAF and method throttles prove too coarse. |

## Sources

Checked on 2026-11-11 against the pages below, except the prices, which are approximate and not re-checked live.

- HTTP API vs REST API: https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html
- API Gateway prices: https://aws.amazon.com/api-gateway/pricing/
- Cognito user pool authorizer (ID token when no scopes): https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-integrate-with-cognito.html
- Request validation and models (draft 4): https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-method-request-validation.html
- Lambda proxy integration, format 1.0 event: https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html
- Usage plans and API keys: https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-api-usage-plans.html
- Throttling: https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-request-throttling.html
- AWS WAF with API Gateway REST API stages: https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-control-access-aws-waf.html
- Resources AWS WAF can protect, and the CloudFront us-east-1 rule: https://docs.aws.amazon.com/waf/latest/developerguide/how-aws-waf-works-resources.html
- Common rule set, including the body size rule: https://docs.aws.amazon.com/waf/latest/developerguide/aws-managed-rule-groups-baseline.html
- Rate-based rules: https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based.html
- WAF prices: https://aws.amazon.com/waf/pricing/
- Project records: 0002 (superseded), 0003 (SNS), 0004 (tagger), 0005 (VPC), `docs/data-model.md` section 3
