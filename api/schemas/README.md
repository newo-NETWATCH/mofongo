# Request schemas

One JSON Schema file per request body, in the draft-4 subset. `openapi.yaml` points at each file with `$ref`.

| File | Body of |
|---|---|
| `post-item.json` | `POST /items` |
| `post-report.json` | `POST /reports` |

## Rules for these files

- Start with `"$schema": "http://json-schema.org/draft-04/schema#"`.
- Use only these keywords: `type`, `properties`, `required`, `enum`, `minLength`, `maxLength`, `pattern`, `minimum`, `maximum`, `items`, `minItems`, `maxItems`, `uniqueItems`, `additionalProperties`.
- Set `"additionalProperties": false` on every object. A body cannot add `finderId`, `ownerId` or `status`.
- Give every string a `maxLength`.
- Use the exact category and color lists from `docs/data-model.md` sections 2.1 and 2.2 as `enum` values.
- Times are only checked for their shape here. The Lambda parses them and refuses a time in the future.

## How the Lambda uses them

HTTP APIs do not validate request bodies. After the token check (401) and the size check (413) described in `api/README.md`, the API Lambda validates each body with `Draft4Validator` before it reads or writes any data:

```python
from jsonschema import Draft4Validator

validator = Draft4Validator(schema)  # load the file once, outside the handler
errors = sorted(validator.iter_errors(body), key=lambda e: list(e.path))
if errors:
    ...  # answer 400 with one entry in "details" for each error
```

- Copy this folder into the Lambda package when you build it.
- Test each file with one good body and a few bad ones.
