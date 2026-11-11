# API schemas

One JSON Schema file per function the web app calls, in the draft-4 subset. Every one of the 10 operations in `openapi.yaml` has at least one schema file: its success-response body. `createItem` and `createReport` also have a request-body schema.

## Layout

```
schemas/
  requests/    bodies the web app sends. Runtime-validated by the API Lambda.
  responses/   success bodies the API returns. One file per operation.
  shared/      reusable objects (item, report, match) and the error envelope.
```

| File | What it describes | Operation |
|---|---|---|
| `requests/create-item.json` | request body | `createItem` (`POST /items`) |
| `requests/create-report.json` | request body | `createReport` (`POST /reports`) |
| `responses/list-items.json` | success body | `listItems` (`GET /items`) |
| `responses/create-item.json` | success body | `createItem` (`POST /items`) |
| `responses/get-item.json` | success body | `getItem` (`GET /items/{itemId}`) |
| `responses/mark-item-returned.json` | success body | `markItemReturned` (`POST /items/{itemId}/returned`) |
| `responses/list-reports.json` | success body | `listReports` (`GET /reports`) |
| `responses/create-report.json` | success body | `createReport` (`POST /reports`) |
| `responses/get-report.json` | success body | `getReport` (`GET /reports/{reportId}`) |
| `responses/close-report.json` | success body | `closeReport` (`POST /reports/{reportId}/closed`) |
| `responses/get-my-alerts.json` | success body | `getMyAlerts` (`GET /me/alerts`) |
| `responses/subscribe-my-alerts.json` | success body | `subscribeMyAlerts` (`POST /me/alerts`) |
| `shared/error.json` | error envelope (`message` and `details[]`) for 4xx and 5xx | all |
| `shared/item.json` | reusable item object | item responses |
| `shared/report.json` | reusable report object | report responses |
| `shared/match.json` | reusable match object | report and alert responses |

## One schema per function

- Add a schema file for every new operation. A route with no request body still gets a response schema.
- Name response files after the `operationId`, in kebab-case (`markItemReturned` becomes `mark-item-returned.json`).
- Name request files `create-<thing>.json` after the operation that sends them.

## Rules for every file

- Start with `"$schema": "http://json-schema.org/draft-04/schema#"`.
- Use only these keywords: `type`, `properties`, `required`, `enum`, `minLength`, `maxLength`, `pattern`, `minimum`, `maximum`, `items`, `minItems`, `maxItems`, `uniqueItems`, `additionalProperties`, `$ref`, `definitions`, `description`.
- Set `"additionalProperties": false` on every object. A request body cannot add `finderId`, `ownerId` or `status`.
- Give every string a `maxLength`.
- Use the exact category and color lists from `docs/data-model.md` sections 2.1 and 2.2 as `enum` values, and the status words from section 2.3.
- Times are only checked for their shape here. The Lambda parses them and refuses a time in the future.

## Responses list only what the endpoint returns

A response schema is an allowlist (excessive data exposure, `securitymaxxing:api`). It names only the fields that endpoint really returns, as set out in `docs/data-model.md` section 7 and the `openapi.yaml` examples.

- Never list internal DynamoDB attributes (sparse-index keys such as `listedPk`, `listedCategory`, `openCategory`).
- Never list other users' identities, subscription ARNs or raw email unless that one endpoint returns them.
- A finder-only or owner-only field appears only in the response that returns it, and its `description` says who may see it.
- List responses use the envelope from `openapi.yaml`: an `items` array and a `nextToken` string with a `maxLength`.

## Runtime schemas and contract schemas

| | `requests/` | `responses/` and `shared/` |
|---|---|---|
| Used by | the API Lambda, at runtime | the web app and the tests |
| `$ref` | not allowed: each file is standalone | allowed: local, relative paths such as `../shared/item.json` |
| Why | the Lambda loads one file at a time | the Lambda never validates responses |

- A request file must inline everything (enums, patterns, lengths). The Lambda validates each file on its own, so an external `$ref` would not resolve.
- Response and shared files may `$ref` the `shared/` definitions. Keep each path relative and make sure it resolves.

## How the Lambda uses the request schemas

HTTP APIs do not validate request bodies. After the token check (401) and the size check (413) described in `api/README.md`, the API Lambda validates each body with `Draft4Validator` before it reads or writes any data:

```python
from jsonschema import Draft4Validator

validator = Draft4Validator(schema)  # load the file once, outside the handler
errors = sorted(validator.iter_errors(body), key=lambda e: list(e.path))
if errors:
    ...  # answer 400 with one entry in "details" for each error
```

- Copy `requests/` into the Lambda package when you build it. `responses/` and `shared/` are not needed at runtime.
- Test each request file with one good body and a few bad ones.
- Check every file with `Draft4Validator.check_schema`. Test each response file against the matching example in `openapi.yaml`.

## Keep the lists in step

The category and color lists are written in these places. Change them in one commit:

- `docs/data-model.md`
- `openapi.yaml`
- `requests/create-item.json`
- `requests/create-report.json`
- `shared/item.json`
- `shared/report.json`
- `shared/match.json`, and any response file that repeats a list
