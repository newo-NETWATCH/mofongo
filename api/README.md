# API

The contract between the web app and the API Lambda. Written in Step 4 of the plan, from [docs/data-model.md](../docs/data-model.md).

| Path | What it is |
|---|---|
| `openapi.yaml` | OpenAPI 3.0.3. All 10 endpoints: who may call each one, what it reads and writes, parameters, answers, errors and examples. |
| `schemas/` | One JSON Schema (draft 4) per request body. See [schemas/README.md](schemas/README.md). |

## Who checks what

- API Gateway HTTP APIs do not check request bodies, query values or path values. The JWT authorizer only checks the token.
- The API Lambda first checks the body size. A body over 32 KiB (32768 bytes, measured after base64 decoding) gets HTTP 413. API Gateway itself only stops bodies over 10 MB.
- The API Lambda then checks every body with Python `jsonschema` (`Draft4Validator`) against its file in `schemas/`, before it does anything else. A body that fails gets HTTP 400.
- The API Lambda checks that the token's `token_use` claim is `id` and that `sub` is present. If not, it answers HTTP 401.
- The Lambda also checks path and query values (UUIDs, `limit`, `category`, `nextToken`) using the rules in `openapi.yaml`.
- Routes with no body (`POST /items/{itemId}/returned`, `POST /reports/{reportId}/closed`, `POST /me/alerts`) have no schema file.

## Keeping the files in step

- The category and color lists are written in four places: `docs/data-model.md`, `openapi.yaml`, `schemas/post-item.json` and `schemas/post-report.json`. Change them in one commit.
- Change `openapi.yaml` and the schema files together. The web app, the Lambda and the tests all read them.

## Checking the files

```
uvx --from openapi-spec-validator openapi-spec-validator api/openapi.yaml
```

- This checks the layout of `openapi.yaml`. It does not open the files in `schemas/`. Check each schema file on its own with `Draft4Validator.check_schema`, and test it with one good body and a few bad ones.
- The schema files keep `$schema` because it names the draft. OpenAPI 3.0 does not allow that key inside a schema, so a strict check of a copy with the files pasted in would reject it.
