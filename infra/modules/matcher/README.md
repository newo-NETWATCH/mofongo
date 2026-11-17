# Module: matcher

The Python 3.13 Lambda that DynamoDB Streams starts (`backend/matcher`). It pairs a newly tagged item with open lost reports, and a newly filed report with listed items, records each pair once, and publishes one email message per new pair. The rules are in `docs/data-model.md` section 6. Same module pattern as `api_lambda`, and it also runs outside the VPC.

The module creates the function, its log group, its least-privilege role, the two event source mappings, and the failure queue `mofongo-dev-matcher-failed`. It does not create the tables, streams or the SNS topic. They are inputs.

## Before `terraform plan`

Build a package folder that holds the matcher code at its top level (default handler `app.handler`; set `handler` if the module has another name). Pass it as `package_dir`. The zip is written next to it as `<package_dir>.zip`. A missing handler file fails at plan with a message. boto3 is not bundled: the Lambda runtime provides it.

## Inputs that must match other modules

| Input | Comes from |
|---|---|
| `table_names`, `table_arns` | `module.dynamodb` (same `object({items, reports, matches, users})` type) |
| `index_names` | `module.dynamodb.index_names` |
| `stream_arns` | `module.dynamodb.stream_arns` (`{items, reports}`) |
| `alerts_topic_arn` | `module.alerts_topic.topic_arn` |
| `site_url` | the site origin the email links to (no trailing slash) |

`index_names` and the rest become environment variables like this:

| Source | Env var |
|---|---|
| `table_names.items`, `.reports`, `.matches` | `ITEMS_TABLE`, `REPORTS_TABLE`, `MATCHES_TABLE` |
| `index_names.items.listed_by_category` | `IDX_LISTED_BY_CATEGORY` |
| `index_names.reports.open_by_category` | `IDX_OPEN_BY_CATEGORY` |
| `index_names.items.listed_by_date`, `index_names.reports.by_owner` | not passed and not granted (the API's) |
| `alerts_topic_arn` | `ALERTS_TOPIC_ARN` |
| `site_url` | `SITE_URL` |
| `match_threshold` (default 60) | `MATCH_THRESHOLD` |
| `log_level` | `LOG_LEVEL` |

`AWS_REGION` is set by Lambda itself.

## Event source mappings (data-model 6.2)

| | Items stream | Reports stream |
|---|---|---|
| Runs when | a `LISTED` item's `tagStatus` goes from `PENDING` to `TAGGED` | a report is INSERTed with `status = OPEN` |
| Direction | A (6.4) | B (6.5) |

Both mappings: `LATEST`, batch size 10, no batching window, 3 retries, records older than 6 hours skipped, `bisect_batch_on_function_error`, `ReportBatchItemFailures`, and given-up records noted in the failure queue. The handler must return `batchItemFailures`.

The filter patterns are built with `jsonencode` in `main.tf`. Test them on the first deploy as data-model 6.2 says: create a report (one run), close it (no run), post an item (no run), let the tagger save tags (one run). If the Reports `exists: false` test fails, drop the `OldImage` part of `reports_filter`.

## What the role can do

| Service | Allowed | Not allowed |
|---|---|---|
| DynamoDB streams | `GetRecords`, `GetShardIterator`, `DescribeStream`, `ListStreams` on the Items and Reports stream ARNs | any other stream |
| DynamoDB | `GetItem` on Items and Reports; `Query` on `ListedByCategory` and `OpenByCategory`; `PutItem`, `UpdateItem`, `DeleteItem` on Matches | `Scan`, `Query` on the table or other indexes, Users, any `Resource: "*"` |
| SNS | `Publish` on the alerts topic | `Subscribe` (the API's job), any other topic |
| SQS | `SendMessage` on `mofongo-dev-matcher-failed` | everything else |
| Logs | `CreateLogStream`, `PutLogEvents` on its own group | `CreateLogGroup` (Terraform owns the group) |

Matches needs `UpdateItem` (AP15, `notifiedAt`) and `DeleteItem` (AP16, undo when SNS refuses) as well as the conditional `PutItem` (AP14), because section 6.7 uses all three. The SQS permission is there because the mappings' `on_failure` destination is sent with this role.

## After the first deploy

- Alarm on `failed_queue_name` having a visible message.
- The SNS alerts topic is shared with the CloudWatch alarms. Matcher messages carry the `ownerId` attribute, so only the owner's filtered subscription receives them.
