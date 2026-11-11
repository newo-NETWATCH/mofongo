# Module: api_lambda

The Python 3.13 Lambda behind the REST API (`backend/api`), its log group, and its least-privilege role.

## Before `terraform plan`

Build the package folder. It holds the handler code, the Linux build of `jsonschema`, and the request and shared schemas copied from `api/schemas`:

```powershell
./scripts/build-api.ps1
```

Pass the folder it prints (`build/api`) as `package_dir`. The zip is written next to it as `build/api.zip`. Both are git-ignored. A missing file fails at plan with a message.

## Inputs that must match other modules

| Input | Comes from |
|---|---|
| `table_names`, `table_arns` | `module.dynamodb` (same `object({items, reports, matches, users})` type) |
| `index_names` | `module.dynamodb.index_names` |
| `photos_bucket_name`, `photos_bucket_arn` | `module.photos_bucket` |
| `alerts_topic_arn` | `module.alerts_topic.topic_arn` |
| `cognito_user_pool_id`, `cognito_app_client_id` | `module.cognito.user_pool_id`, `module.cognito.app_client_id` |
| `cors_origin` | the same site origin the `api` and `photos_bucket` modules use |

`index_names` becomes environment variables like this:

| `index_names` key | Env var |
|---|---|
| `items.listed_by_date` | `IDX_LISTED_BY_DATE` |
| `items.listed_by_category` | `IDX_LISTED_BY_CATEGORY` |
| `reports.by_owner` | `IDX_BY_OWNER` |
| `reports.open_by_category` | not passed and not granted (the matcher reads it) |

## What the role can do

| Service | Allowed | Not allowed |
|---|---|---|
| DynamoDB | `GetItem`, `PutItem`, `UpdateItem`, `BatchGetItem` on Items; `GetItem`, `PutItem`, `UpdateItem` on Reports; `GetItem`, `PutItem` on Users; `Query` on Matches, `ListedByDate`, `ListedByCategory`, `ByOwner` | `Scan`, `DeleteItem`, `OpenByCategory`, streams, any `Resource: "*"` |
| SNS | `Subscribe` (email only) and `GetSubscriptionAttributes` on the alerts topic | `Publish` (the matcher's job) |
| S3 | `PutObject` and `GetObject` on `photos/*` (to presign) | `ListBucket`, `DeleteObject`, anything bucket-level |
| Logs | `CreateLogStream`, `PutLogEvents` on its own group | `CreateLogGroup` (Terraform owns the group) |

One role serves every route and caller, so IAM cannot keep one user's rows from another. The code does that by building keys from the token's `sub`.
