# Mofongo data model

Draft for review, 21 Oct 2026. This is Step 4, items 1 and 2 of [plan.md](plan.md): the screens, and the DynamoDB tables, indexes and access patterns behind them. `api/openapi.yaml` and the JSON Schemas (Step 4, item 3) are written from this file.

How it was made: the access patterns were listed first, then the keys and indexes were chosen to answer each one, following the AWS DynamoDB data-modeling method. Facts about AWS limits and syntax were checked against AWS documentation (links at the end).

## What is kept and what changed from the plan

| Topic | Result |
|---|---|
| Table names | Kept: Items, Reports, Matches, Users. |
| Index names | Kept: ListedByDate, ListedByCategory, OpenByCategory, ByOwner. |
| Endpoints | The eight in plan Part 3, plus two marked "added" (section 1). |
| Reports primary key | The draft did not name it. It is `ownerId` + `reportId` (section 4.2 says why). |
| New attributes | `tagError` (Items), `closedAt` (Reports), `scoreParts` (Matches). |
| One extra AWS resource | A small SQS queue that catches stream records the matching Lambda could not process (section 6.2). |

## 1. Screens

Sign-in is Cognito managed login and is not one of these screens. Every endpoint needs a signed-in user. The user's ID is the `sub` claim of the ID token. It is never read from the request body or the URL.

### 1.1 Browse items

- **Shows:** listed items, newest first. Each card has a thumbnail, title, category, colors, where it was found and when it was posted. A row of category buttons (section 2.1) narrows the list. Items whose tags are not ready yet are shown too.
- **Does:** pick a category or "All". "Load more" fetches the next page with `nextToken`.
- **Calls:** `GET /items`, with optional `category`, `limit` (default 20, at most 50) and `nextToken`.
- **Photos:** each item comes with a short-lived photo link that the API makes from `photoKey`. The link is not stored. A `wallet-id` item has no link unless the caller is the finder (see "Who can see what" in section 4). The card shows a placeholder.

### 1.2 Item detail

- **Shows:** a large photo, title, description, category, colors, where and when found, and the status (`LISTED` or `RETURNED`). A small line says whether the photo has been analyzed (`tagStatus`). The finder also sees a "Mark returned" button while the item is `LISTED`.
- **Does:** the finder marks the item returned after the owner collects it at the front desk.
- **Calls:** `GET /items/{itemId}`, then `POST /items/{itemId}/returned`.
- **Privacy:** other users never get the finder's ID. The API sends `isMine` (true or false) instead.

### 1.3 Post item

- **Shows:** a form with title, description (optional), category, colors (1 to 3), where found, when found, and one photo (up to 10 MB).
- **Does:** sends the form and gets back the item ID and a presigned POST. The browser then uploads the photo straight to S3 as `photos/{itemId}.jpg`. That upload is not an API call. The page then opens the item detail.
- **Calls:** `POST /items`.

### 1.4 File a lost report

- **Shows:** a form with category, colors (1 to 3), description, where lost (optional) and when lost (optional).
- **Does:** sends the form. The answer includes an `alerts` field that says how email alerts stand: `started` (a confirmation email was just sent), `existing` (a subscription is already saved), `no-verified-email` (alerts are not possible) or `unavailable` (SNS refused, see section 8.5). The page shows the matching message.
- **Calls:** `POST /reports`.

### 1.5 My reports

- **Shows:** the user's reports, newest first: category, colors, the start of the description, the status (`OPEN` or `CLOSED`) and the date filed. A banner shows the email alert state.
- **Does:** open a report, load more.
- **Calls:** `GET /reports` with `limit` and `nextToken`. The banner uses `GET /me/alerts`.

### 1.6 Report detail

- **Shows:** the report, then its matches with the best score first. Each match shows the photo, title, category, colors, where and when found, whether the item is still `LISTED` or already `RETURNED`, the score and the "why" lines.
- **Does:** the owner closes the report when the item is collected or they stop looking. A closed report stops being matched. A match that was already being worked on when the owner closed it can still arrive in the first seconds (section 6.8).
- **Calls:** `GET /reports/{reportId}`, then `POST /reports/{reportId}/closed` (added).

### 1.7 Email alert status

- **Shows:** one of four states (table below) and what to do about it.
- **Does:** a button sends the confirmation email again or subscribes again.
- **Calls:** `GET /me/alerts`, then `POST /me/alerts` (added).

| State | Meaning | The page offers |
|---|---|---|
| `NONE` | No subscription is saved. No report was filed yet, or the email was not verified. | Subscribe (needs a verified email) |
| `UNCONFIRMED` | A subscription exists but the owner has not clicked "Confirm subscription". The link works for 48 hours. | Send the confirmation email again |
| `CONFIRMED` | Alerts are on. | Nothing |
| `GONE` | A subscription is saved, but SNS no longer has it. It expired after 48 hours unconfirmed, or the owner clicked unsubscribe. | Subscribe again |

The plan calls `UNCONFIRMED` "pending". It has a different name here so it is not mixed up with `tagStatus = PENDING`. These four states are only sent by the API. They are never stored.

### Endpoints

| Endpoint | Does | Source |
|---|---|---|
| `GET /items` | Browse listed items, newest first, optionally by category | plan |
| `POST /items` | Post a found item. Returns the item ID and a presigned POST for the photo | plan |
| `GET /items/{itemId}` | One item, with a short-lived photo link | plan |
| `POST /items/{itemId}/returned` | Mark returned (the finder only) | plan |
| `POST /reports` | File a lost report and subscribe the owner's email | plan |
| `GET /reports` | My reports | plan |
| `GET /reports/{reportId}` | One report and its matches (the owner only) | plan |
| `GET /me/alerts` | Email alert state | plan |
| `POST /reports/{reportId}/closed` | Close my report | **added** |
| `POST /me/alerts` | Subscribe my email again | **added** |

Why the two were added:
- **`POST /reports/{reportId}/closed`:** without it an `OPEN` report stays in OpenByCategory for ever. An owner who already has the item back would keep getting match emails. Closing removes `openCategory`, so the report leaves the index and matching stops.
- **`POST /me/alerts`:** `GET /me/alerts` can answer `GONE`, but nothing could fix it. `POST /reports` only subscribes when no subscription is saved, so it never repairs an expired one.

Not added: a list of "my posted items". The finder opens their item from Browse (it shows an `isMine` badge). If that turns out to be awkward, the fix is `GET /items?mine=true` backed by one more sparse index.

## 2. Shared vocabulary

The same words are used by the post-item form, the report form, the tagger's text prompts, the JSON Schemas and the matching code. Values are lowercase kebab-case. The label is only for display.

### 2.1 Categories (14)

The tagger asks CLIP "a photo of {CLIP phrase}" for every category except `other`.

| Value | Label | CLIP phrase |
|---|---|---|
| `phone` | Phone | a smartphone |
| `laptop-tablet` | Laptop or tablet | a laptop or a tablet computer |
| `headphones` | Headphones or earbuds | headphones or wireless earbuds |
| `charger-cable` | Charger or cable | a phone charger or a cable |
| `wallet-id` | Wallet or ID card | a wallet or an ID card |
| `keys` | Keys | a set of keys or a key fob |
| `bag` | Backpack or bag | a backpack or a bag |
| `water-bottle` | Water bottle or mug | a water bottle or a mug |
| `clothing` | Clothing | a jacket, hoodie, hat or scarf |
| `glasses` | Glasses | eyeglasses or sunglasses |
| `jewelry-watch` | Jewelry or watch | a piece of jewelry or a wristwatch |
| `books-notes` | Books or notebooks | a book or a notebook |
| `calculator-supplies` | Calculator or school supplies | a calculator or school supplies |
| `other` | Other | (none) |

### 2.2 Colors (12)

The tagger asks CLIP "a photo of a {CLIP word} object" for every color.

| Value | Label | CLIP word |
|---|---|---|
| `black` | Black | black |
| `white` | White | white |
| `gray` | Gray | gray |
| `red` | Red | red |
| `orange` | Orange | orange |
| `yellow` | Yellow | yellow |
| `green` | Green | green |
| `blue` | Blue | blue |
| `purple` | Purple | purple |
| `pink` | Pink | pink |
| `brown` | Brown | brown |
| `multicolor` | Multicolor | multicolored |

Hint text for the forms: silver is gray, gold is yellow, tan and beige are brown.

### 2.3 Fixed status words

| Field | Values |
|---|---|
| `Items.status` | `LISTED`, `RETURNED` |
| `Items.tagStatus` | `PENDING`, `TAGGED`, `FAILED` |
| `Reports.status` | `OPEN`, `CLOSED` |
| Alert state (API only) | `NONE`, `UNCONFIRMED`, `CONFIRMED`, `GONE` |

### 2.4 Rules for these lists

- The forms build their buttons from the lists.
- The JSON Schemas use the lists as `enum` values. When a list changes, change the forms, the schemas, the tagger and this file in one commit.
- The API rejects any value that is not in a list with HTTP 400.
- The tagger leaves `other` out, because there is nothing sensible to compare it with. CLIP never says "other", so a pair in `other` gets no CLIP points for category and can score at most 85 (section 6.3).
- Matching compares stored values only. It never matches on text.
- Adding a value is safe. Renaming or removing a value that is already stored breaks old items and reports, so do not.

## 3. Conventions

| Topic | Rule |
|---|---|
| Table names | `mofongo-dev-items`, `mofongo-dev-reports`, `mofongo-dev-matches`, `mofongo-dev-users`. The pattern is `mofongo-<env>-<name>`, so a second environment cannot clash. Index names are unique inside their table and are written as in this file. |
| Billing | On-demand (`PAY_PER_REQUEST`) on every table. No capacity numbers anywhere. |
| IDs | UUID v4 strings made by the server (`str(uuid.uuid4())`). The client never picks an ID. The API checks that every ID in a URL looks like a UUID before it calls DynamoDB. Cognito's `sub` is also a UUID string. |
| Who the user is | `finderId`, `ownerId` and `userId` always come from the `sub` claim of the verified ID token. Never from the body, the query string or the URL. The API Lambda also checks that the token's `token_use` claim is `id`, because the JWT authorizer would let an access token from the same app client through. If the claims or `sub` are missing (a route left without the authorizer), it answers 401, so that mistake fails closed. |
| Timestamps | ISO 8601 in UTC, always the same shape: `2026-10-21T14:05:09.123Z` (milliseconds, `Z` at the end). Equal width means text order is time order, so they work as sort keys. The API converts times typed by users to this shape. A found or lost time may not be in the future. |
| Attribute names | camelCase. |
| Numbers | Whole numbers only. Scores are whole percents. boto3 refuses Python floats. Reads give numbers back as `decimal.Decimal`, and `json.dumps` fails on a `Decimal`. Turn them into `int` before sending an answer (for example `json.dumps(obj, default=int)`). |
| Lists | Use lists (`L`), not sets. A set cannot be empty and has no order. |
| Empty values | Never store an empty string. If a value is missing, leave the attribute out. A sparse index attribute must be removed, not blanked. |
| Reserved words | `status` is a DynamoDB reserved word. In expressions write `#status` and pass `ExpressionAttributeNames={"#status": "status"}`. |
| Creating | A `PutItem` that must not overwrite carries `attribute_not_exists(<key>)`. A failure becomes HTTP 409. |
| Updating | An `UpdateItem` on a row that must already exist carries `attribute_exists(<key>)`. Without it DynamoDB quietly creates a new, nearly empty row. A failure becomes HTTP 404, 403 or 409 (section 5). |
| Reads | `GetItem` uses `ConsistentRead=true`. Index queries can only be eventually consistent. Never pass `ConsistentRead` on an index query: it fails with a ValidationException. |
| Pagination | Described next. |

### Pagination

Every list endpoint takes `limit` (default 20, at most 50) and `nextToken`. It returns `nextToken` whenever DynamoDB returned `LastEvaluatedKey`. That can happen on the last page, so the next page may be empty.

`nextToken` is an opaque string. The server builds it from `LastEvaluatedKey` like this:

1. Make a small JSON object `{"q": "<query id>", "k": <LastEvaluatedKey>}`.
2. Encode it as base64url.

The query id names the index and the partition key value the request is about:

| Request | Query id |
|---|---|
| `GET /items` | `ListedByDate\|LISTED` |
| `GET /items?category=water-bottle` | `ListedByCategory\|water-bottle` |
| `GET /reports` | `ByOwner\|<the caller's sub>` |

Before the server uses a token it must do all of these. If any step fails it answers HTTP 400 and does not query.

1. Decode it. Anything that does not decode is rejected.
2. Build the query id for the current request and compare it with `q`. If they differ, the token belongs to another query.
3. Check that `k` has exactly the key attributes of that index (for example `listedCategory`, `createdAt`, `itemId`) and that its partition key value equals the current request's value.
4. Only then pass `k` as `ExclusiveStartKey`.

Why: the token travels through the browser, so the user can edit it. The `ByOwner` case matters most. A token from one user must never be able to start a query for another user. Do not rely on DynamoDB to refuse a wrong start key. Signing the token with an HMAC would also catch edits, but it is not required: a forged start key in the right partition only changes where the page starts, inside data the caller may already see.

A token holds a position, not a snapshot. It has no expiry. If rows were added or removed meanwhile, the next page just continues from that position.

## 4. Tables

All four tables use on-demand billing, no TTL, the default encryption (an AWS-owned key) and the Standard table class.

| Table | Primary key | Indexes | Stream | Point-in-time recovery | Deletion protection |
|---|---|---|---|---|---|
| `mofongo-dev-items` | `itemId` | ListedByDate, ListedByCategory | `NEW_AND_OLD_IMAGES` | on | on |
| `mofongo-dev-reports` | `ownerId` + `reportId` | ByOwner, OpenByCategory | `NEW_AND_OLD_IMAGES` | on | on |
| `mofongo-dev-matches` | `reportId` + `itemId` | none | off | on | on |
| `mofongo-dev-users` | `userId` | none | off | on | on |

Why four tables: they are read by different keys, and only Items and Reports have a stream. Settings that differ per table are a reason for separate tables. Nothing is read together with something from another table in one request, so nothing is pre-joined.

### Who can see what

This check comes first because it is the most common DynamoDB security mistake: a key built from an ID the client supplied lets a caller reach rows that are not theirs.

| Table | Who may read | How the design enforces it |
|---|---|---|
| Items | Every signed-in user | The rows hold nothing private, so the key is `itemId`. Changing an item (mark returned) is guarded by a condition `finderId = :sub`. `finderId` is never sent to other users. The photo can be private: a `wallet-id` photo may show a name, a face or card numbers. So Browse and item detail send no photo link for a `wallet-id` item unless the caller is the finder. A match inside `GET /reports/{reportId}` still has the link. The post-item form asks finders not to photograph the front of a card. |
| Reports | The owner only | The key starts with `ownerId`, which the API takes from the token. A caller cannot name another owner's report: `GetItem` with their own `ownerId` finds nothing. `ByOwner` queries also use the token's `sub`. |
| Matches | The owner of the report | Matches are keyed by `reportId` alone, so the key does not protect them. The API only queries Matches after AP11 (section 5) has shown the report belongs to the caller. Keep those two calls together in one function and test them. |
| Users | The user themselves | The key is the token's `sub`. |

### 4.1 Items

**Purpose:** one row per found item.

**Primary key:** `itemId` (S), no sort key.

| Name | Type | Required | Written by | Notes |
|---|---|---|---|---|
| `itemId` | S | yes | API | Table key. UUID v4. |
| `finderId` | S | yes | API | Cognito `sub` of the finder. Never sent to other users. |
| `title` | S | yes | API | 1 to 80 characters. |
| `description` | S | no | API | Up to 1000 characters. Left out when empty. |
| `category` | S | yes | API | One of the values in section 2.1. Never changes. |
| `colors` | L of S | yes | API | 1 to 3 values from section 2.2, no repeats. |
| `foundLocation` | S | yes | API | Free text, 1 to 200 characters, for example "Library, first floor". |
| `foundAt` | S | yes | API | When it was found. ISO 8601 UTC. |
| `status` | S | yes | API | `LISTED` when posted. `RETURNED` after the finder marks it returned. |
| `photoKey` | S | yes | API | `photos/{itemId}.jpg`. Set when the item is created, before the photo is uploaded. |
| `tagStatus` | S | yes | API, then tagger | `PENDING` when created. The tagger sets `TAGGED` or `FAILED`. |
| `clipTags` | M | no | tagger | Only when `TAGGED`. Has `categories` and `colors`. Each is a list of the top 3 as `{value, score}`, where `score` is a whole percent from 0 to 100. |
| `taggedAt` | S | no | tagger | When the tags were saved. |
| `tagError` | S | no | tagger | Short reason. Only when `FAILED`. |
| `createdAt` | S | yes | API | When the item was posted. Sort key of both indexes. |
| `returnedAt` | S | no | API | When the finder marked it returned. |
| `listedPk` | S | no | API | Sparse index key. The text `LISTED` while the item is listed. |
| `listedCategory` | S | no | API | Sparse index key. A copy of `category` while the item is listed. |

**Indexes:**

| Index | Partition key | Sort key | Projection | In the index when | Leaves the index when |
|---|---|---|---|---|---|
| ListedByDate | `listedPk` (S) | `createdAt` (S) | ALL | `listedPk` is set. `POST /items` writes `listedPk = "LISTED"`. | `POST /items/{itemId}/returned` removes `listedPk`, in the same update that sets `status = RETURNED`. |
| ListedByCategory | `listedCategory` (S) | `createdAt` (S) | ALL | `listedCategory` is set. `POST /items` writes it, equal to `category`. | The same update removes `listedCategory`. |

Rules for the two sparse keys:
- Only `POST /items` sets them and only `POST /items/{itemId}/returned` removes them. Nothing else touches them.
- `category` never changes, so `listedCategory` never needs updating.
- DynamoDB adds an item to an index only while every key attribute of that index is present on it. That is the whole mechanism, and why returned items drop out by themselves.

Why `ALL` on both: browse needs most attributes, and matching needs `colors` and `clipTags`. An index projection cannot be changed later, items are small, and tuning the score in week 6 may need other attributes. A tag update also rewrites the index entries, which is fine at this size.

**Stream:** on, `NEW_AND_OLD_IMAGES`. The matching Lambda is the only reader (section 6).

**Example item** (plain JSON, not DynamoDB JSON):

```json
{
  "itemId": "7b1f6f0e-3c58-4a53-9d0e-5a1c2f6d9a11",
  "finderId": "a3c4e5f6-1111-4222-8333-944455556666",
  "title": "Black Hydro Flask",
  "description": "32 oz bottle with a green sticker on the side. Found on a bench.",
  "category": "water-bottle",
  "colors": ["black", "green"],
  "foundLocation": "Library, first floor",
  "foundAt": "2026-10-20T16:30:00.000Z",
  "status": "LISTED",
  "photoKey": "photos/7b1f6f0e-3c58-4a53-9d0e-5a1c2f6d9a11.jpg",
  "tagStatus": "TAGGED",
  "clipTags": {
    "categories": [
      { "value": "water-bottle", "score": 81 },
      { "value": "keys", "score": 6 },
      { "value": "headphones", "score": 4 }
    ],
    "colors": [
      { "value": "black", "score": 62 },
      { "value": "green", "score": 21 },
      { "value": "gray", "score": 9 }
    ]
  },
  "taggedAt": "2026-10-20T16:41:12.481Z",
  "createdAt": "2026-10-20T16:38:55.207Z",
  "listedPk": "LISTED",
  "listedCategory": "water-bottle"
}
```

### 4.2 Reports

**Purpose:** one row per lost report.

**Primary key:** `ownerId` (S, partition key) + `reportId` (S, sort key).

Why this key: reports are private. With `ownerId` first, the API builds every key from the token's `sub`, so a caller cannot reach another owner's report (see "Who can see what"). The plan's draft did not name a key. A key of `reportId` alone would have needed an ownership check in code on every call.

| Name | Type | Required | Written by | Notes |
|---|---|---|---|---|
| `ownerId` | S | yes | API | Partition key. Cognito `sub` of the owner, from the token. |
| `reportId` | S | yes | API | Sort key. UUID v4. |
| `category` | S | yes | API | One of the values in section 2.1. |
| `colors` | L of S | yes | API | 1 to 3 values from section 2.2, no repeats. |
| `description` | S | yes | API | 1 to 1000 characters. |
| `lostLocation` | S | no | API | Free text, up to 200 characters. Optional because owners often do not know. |
| `lostAt` | S | no | API | When it was lost, ISO 8601 UTC. Optional. |
| `status` | S | yes | API | `OPEN` when filed. `CLOSED` after the owner closes it. |
| `openCategory` | S | no | API | Sparse index key. A copy of `category` while the report is `OPEN`. |
| `createdAt` | S | yes | API | When the report was filed. Sort key of both indexes. |
| `closedAt` | S | no | API | When the owner closed it. |

**Indexes:**

| Index | Partition key | Sort key | Projection | In the index when | Leaves the index when |
|---|---|---|---|---|---|
| ByOwner | `ownerId` (S) | `createdAt` (S) | ALL | Always. Every report has both keys, so this index is not sparse. | Never. |
| OpenByCategory | `openCategory` (S) | `createdAt` (S) | ALL | `openCategory` is set. `POST /reports` writes it, equal to `category`. | `POST /reports/{reportId}/closed` removes `openCategory`, in the same update that sets `status = CLOSED`. |

Why ByOwner exists when the table key already starts with `ownerId`: the table keeps one owner's reports together but orders them by the random `reportId`. ByOwner gives newest first.

Why `ALL` on both: same reason as Items. Reports are about 1 KB.

**Stream:** on, `NEW_AND_OLD_IMAGES`. The matching Lambda reads it, filtered to new reports only (section 6).

**Example report:**

```json
{
  "ownerId": "5d2c9a10-8f3e-4b77-a1c2-0e9b7d6f4a33",
  "reportId": "c0a8e7d4-62b1-4c9f-8d35-1f7a9b2e6c40",
  "category": "water-bottle",
  "colors": ["black"],
  "description": "Black 32 oz Hydro Flask with a dent near the bottom.",
  "lostLocation": "Science building, room 210",
  "lostAt": "2026-10-20T15:00:00.000Z",
  "status": "OPEN",
  "openCategory": "water-bottle",
  "createdAt": "2026-10-20T18:02:41.516Z"
}
```

### 4.3 Matches

**Purpose:** one row per matched pair of report and item. It does two jobs: it shows an owner their matches, and it remembers which pairs were already emailed.

**Primary key:** `reportId` (S, partition key) + `itemId` (S, sort key).

Why this key: all matches of one report sit in one partition, so "a report's matches" is one Query. "Was this pair already handled?" uses the same key, so the conditional write is the check. No index: nothing asks "which reports matched this item".

| Name | Type | Required | Written by | Notes |
|---|---|---|---|---|
| `reportId` | S | yes | matching Lambda | Partition key. |
| `itemId` | S | yes | matching Lambda | Sort key. |
| `score` | N | yes | matching Lambda | Whole number from 0 to 100 (section 6.3). |
| `scoreParts` | M | yes | matching Lambda | Whole numbers: `category`, `colors`, `clipCategory`, `clipColor`. They add up to `score`. |
| `why` | L of S | yes | matching Lambda | 2 to 4 short plain sentences. The report detail screen shows them. |
| `createdAt` | S | yes | matching Lambda | When the match was recorded. |
| `notifiedAt` | S | no | matching Lambda | When SNS accepted the email message. Missing until then. It means "handed to SNS", not "delivered". |

**Stream:** off. **Written only by the matching Lambda. Read by the API.**

**Example match** (for the example item and report above):

```json
{
  "reportId": "c0a8e7d4-62b1-4c9f-8d35-1f7a9b2e6c40",
  "itemId": "7b1f6f0e-3c58-4a53-9d0e-5a1c2f6d9a11",
  "score": 91,
  "scoreParts": { "category": 40, "colors": 30, "clipCategory": 12, "clipColor": 9 },
  "why": [
    "Same category: Water bottle or mug",
    "Shared color: black",
    "The photo looks like a water bottle or a mug (81%)",
    "The photo looks black (62%)"
  ],
  "createdAt": "2026-10-20T18:02:43.902Z",
  "notifiedAt": "2026-10-20T18:02:44.310Z"
}
```

### 4.4 Users

**Purpose:** remembers each user's email alert subscription, so the API does not subscribe twice and can ask SNS for its state.

**Primary key:** `userId` (S), no sort key.

| Name | Type | Required | Written by | Notes |
|---|---|---|---|---|
| `userId` | S | yes | API | Table key. Cognito `sub`. |
| `subscriptionArn` | S | yes | API | From `Subscribe` with `ReturnSubscriptionArn=true`, so it is a real ARN even before the owner confirms. |
| `subscribedAt` | S | yes | API | When the subscription was made. |

No email address is stored. The API reads `email` and `email_verified` from the ID token each time it subscribes.

**Stream:** off. No index.

**Example user:**

```json
{
  "userId": "5d2c9a10-8f3e-4b77-a1c2-0e9b7d6f4a33",
  "subscriptionArn": "arn:aws:sns:us-east-2:123456789012:mofongo-dev-alerts:1328f057-de93-4c15-512e-8bb22EXAMPLE",
  "subscribedAt": "2026-10-20T18:02:41.900Z"
}
```

The topic name `mofongo-dev-alerts` is a placeholder until the SNS step.

## 5. Access patterns

Rules this table follows:
- **No Scan anywhere.** Every pattern is a `GetItem`, a `BatchGetItem`, a `Query`, or a single-row write.
- **No `FilterExpression`.** Every selection is made by a key or an index. The one check done in code after a query is in the matching Lambda (AP18): it skips the few listed items that have no tags yet. That removes a handful of rows. The index already did the selecting.
- **Writes carry conditions** as described in section 3.
- **Index queries are eventually consistent.** Section 8.3 says what that means for the screens.

| # | Pattern | Who uses it | Table or index | Operation | Notes |
|---|---|---|---|---|---|
| AP1 | All listed items, newest first | `GET /items` | Items, ListedByDate | `Query` `listedPk = :v` (`:v` is `LISTED`), `ScanIndexForward=false`, `Limit=:limit`, `ExclusiveStartKey` from the checked token | Paged. Token query id `ListedByDate\|LISTED`. |
| AP2 | Listed items in one category, newest first | `GET /items?category=` | Items, ListedByCategory | `Query` `listedCategory = :category`, `ScanIndexForward=false`, `Limit`, `ExclusiveStartKey` | Paged. The category is checked against section 2.1 first (HTTP 400 if unknown). |
| AP3 | One item | `GET /items/{itemId}`; matching Lambda (re-read) | Items, table key | `GetItem` `{itemId}`, `ConsistentRead=true` | No item: HTTP 404. A `RETURNED` item can still be read. |
| AP4 | Post an item | `POST /items` | Items | `PutItem` with `status = LISTED`, `tagStatus = PENDING`, `listedPk = LISTED`, `listedCategory = :category`; condition `attribute_not_exists(itemId)` | The API writes the item first and hands out the upload form second, so the tagger always finds the item. |
| AP5 | Save tags | Tagger | Items | `UpdateItem` `{itemId}`: `SET tagStatus = :tagged, clipTags = :tags, taggedAt = :now`; condition `attribute_exists(itemId) AND tagStatus = :pending` | If the condition fails, the item is gone or already tagged. The tagger treats the queue message as done. This makes `PENDING` to `TAGGED` happen once. |
| AP6 | Mark tagging failed | Tagger | Items | `UpdateItem` `{itemId}`: `SET tagStatus = :failed, tagError = :msg`; same condition as AP5 | Used when the photo cannot be read or the last retry fails. |
| AP7 | Mark returned | `POST /items/{itemId}/returned` | Items | `UpdateItem` `{itemId}`: `SET #status = :returned, returnedAt = :now REMOVE listedPk, listedCategory`; condition `attribute_exists(itemId) AND finderId = :sub AND #status = :listed`; `ReturnValues=ALL_NEW`; `ReturnValuesOnConditionCheckFailure=ALL_OLD` | On success the 200 answer is built from `Attributes` (drop `finderId`, add `isMine`), so no second read is needed. On failure read the old row: no row, HTTP 404; `finderId` differs, HTTP 403; status already `RETURNED`, HTTP 409. |
| AP8 | The items behind a report's matches | `GET /reports/{reportId}` | Items, table key | `BatchGetItem` on up to 100 `{itemId}` keys (from AP13) | Retry `UnprocessedKeys` with backoff. Eventually consistent is fine here. |
| AP9 | File a report | `POST /reports` | Reports | `PutItem` with `status = OPEN`, `openCategory = :category`; condition `attribute_not_exists(reportId)` | The key is `{ownerId: :sub, reportId}`. |
| AP10 | My reports, newest first | `GET /reports` | Reports, ByOwner | `Query` `ownerId = :sub`, `ScanIndexForward=false`, `Limit`, `ExclusiveStartKey` | Paged. Token query id `ByOwner\|<sub>`. The partition value always comes from the token. |
| AP11 | One of my reports | `GET /reports/{reportId}` | Reports, table key | `GetItem` `{ownerId: :sub, reportId}`, `ConsistentRead=true` | Someone else's report ID finds nothing: HTTP 404. |
| AP12 | Close my report | `POST /reports/{reportId}/closed` | Reports | `UpdateItem` `{ownerId: :sub, reportId}`: `SET #status = :closed, closedAt = :now REMOVE openCategory`; condition `attribute_exists(reportId) AND #status = :open`; `ReturnValues=ALL_NEW`; `ReturnValuesOnConditionCheckFailure=ALL_OLD` | On success the 200 answer is built from `Attributes` (drop `ownerId`). No row: HTTP 404. Already `CLOSED`: HTTP 409. |
| AP13 | A report's matches | `GET /reports/{reportId}` | Matches, table key | `Query` `reportId = :r`, `Limit=100` | Run only after AP11 succeeded. The Lambda sorts by `score`, highest first. |
| AP14 | Record a match, once | Matching Lambda | Matches | `PutItem`; condition `attribute_not_exists(reportId)` | `ConditionalCheckFailedException` means the pair was already recorded: stop, send nothing. |
| AP15 | Mark a match as emailed | Matching Lambda | Matches | `UpdateItem` `{reportId, itemId}`: `SET notifiedAt = :now`; condition `attribute_exists(reportId)` | Runs after SNS accepted the message. |
| AP16 | Undo a match when SNS refused the message | Matching Lambda | Matches | `DeleteItem` `{reportId, itemId}`; condition `attribute_not_exists(notifiedAt)` | Only on a clear refusal from SNS (a `ClientError`), so the retry can record and send it again. Not on a timeout (section 6.7). |
| AP17 | Open reports in a category | Matching Lambda (new tagged item) | Reports, OpenByCategory | `Query` `openCategory = :category`, newest first; follow `LastEvaluatedKey` | Stops after 500 candidates and logs a warning. |
| AP18 | Listed items in a category | Matching Lambda (new report) | Items, ListedByCategory | `Query` `listedCategory = :category`, newest first; follow `LastEvaluatedKey` | Same index as AP2. Stops after 500. Items with `tagStatus` other than `TAGGED` are handled as in section 6.5. |
| AP19 | A user's subscription | `POST /reports`; `GET /me/alerts` | Users, table key | `GetItem` `{userId: :sub}`, `ConsistentRead=true` | No row means state `NONE`. |
| AP20 | Save a user's subscription | `POST /reports` (first time); `POST /me/alerts` | Users | `PutItem` `{userId, subscriptionArn, subscribedAt}`, no condition | Overwrites on purpose: a new subscription replaces the old ARN. |

## 6. Streams and matching

### 6.1 Stream settings

| Table | Stream | View type | Reader |
|---|---|---|---|
| Items | on | `NEW_AND_OLD_IMAGES` | matching Lambda, filtered |
| Reports | on | `NEW_AND_OLD_IMAGES` | matching Lambda, filtered |
| Matches, Users | off | none | none |

- The item filter needs `OldImage`, so Items needs `NEW_AND_OLD_IMAGES`. Reports uses the same setting so there is one rule to remember.
- Stream records are kept for 24 hours and are delivered at least once. The same record can arrive twice.
- Turning a stream off and on again creates a new stream ARN, and the event source mapping would need to be recreated. Leave the streams on.

### 6.2 Event source mappings and filters

There are two mappings, one per stream, and both start the same matching Lambda. Lambda checks each record against the filter before it invokes the function. A record that fails the filter is skipped and costs nothing.

Both filters use only the `dynamodb` key, because the Lambda page for DynamoDB filtering says these mappings "only support filtering on the `dynamodb` key".

**Items filter.** Runs when a listed item gets its tags. It needs no `eventName`: an `OldImage` only exists on a change, so this can only match a `MODIFY`.

```json
{
  "dynamodb": {
    "NewImage": {
      "status": { "S": ["LISTED"] },
      "tagStatus": { "S": ["TAGGED"] }
    },
    "OldImage": {
      "tagStatus": { "S": ["PENDING"] }
    }
  }
}
```

**Reports filter.** Runs when a report is created. A new report has no `OldImage`, so `exists: false` on a leaf of `OldImage` matches only an `INSERT`. The `exists` operator only works on leaf nodes, which is why it tests `reportId.S` and not `OldImage` itself.

```json
{
  "dynamodb": {
    "NewImage": {
      "status": { "S": ["OPEN"] }
    },
    "OldImage": {
      "reportId": { "S": [{ "exists": false }] }
    }
  }
}
```

How to read these:
- Keys in one pattern are ANDed. The listed values for one key are ORed. A mapping can hold up to 5 patterns, which are ORed.
- DynamoDB values are written with their type: `{ "S": ["LISTED"] }`.
- Put `NewImage` and `OldImage` inside one `dynamodb` object. The Lambda page shows an AND example that repeats the key `"dynamodb"` twice in one pattern. Most JSON tools keep only the last copy, so the AND would be lost.
- In Terraform write the pattern with `jsonencode()` inside `filter_criteria { filter { pattern = ... } }`. With the AWS CLI the pattern is a JSON string inside `{"Filters": [{"Pattern": "..."}]}`, with the quotes escaped.
- Numbers are compared as text in DynamoDB filters. These two filters use only text values.

**Test the filters on the first deploy.** The `exists: false` test on a missing `OldImage` is not shown on an AWS page, so check it:

1. Create a report. The Lambda must run once.
2. Close that report. The Lambda must not run.
3. Post an item. The Lambda must not run. When the tagger saves its tags, the Lambda must run once.

If step 1 fails, drop the `OldImage` part of the Reports filter and keep only `NewImage.status = OPEN`. That does the same job only because reports change in one way: they get closed, and then `status` is `CLOSED`. If a later change adds updates to open reports (for example a match counter), the matching Lambda would run on each update. That is harmless because of the Matches check, but it is wasted work.

About `eventName`: DynamoDB's own filtering tutorial lists it as a field you can filter on, but the Lambda page says only `dynamodb` is supported. Do not rely on it. Try `{"eventName": ["INSERT"]}` only if both forms above fail the test.

**Settings on both mappings:**

| Setting | Value | Why |
|---|---|---|
| `starting_position` | `LATEST` | The tables are new. |
| `batch_size` | 10 | Small batches. Traffic is low. |
| `maximum_batching_window_in_seconds` | 0 | Run at once. |
| `maximum_retry_attempts` | 3 | Skip a bad record quickly. The default is endless, and one bad record would block its shard for the 24 hours the stream keeps it. A function error uses up the 3 retries within minutes (splitting a batch does not count as a retry), so a broken deploy makes records skip, not wait. Use the replay step below to run them again. |
| `maximum_record_age_in_seconds` | 21600 (6 hours) | Only matters when Lambda cannot start the function at all (for example throttling). Then records wait up to 6 hours before they are skipped. |
| `bisect_batch_on_function_error` | true | A bad record is split off from the good ones. |
| `function_response_types` | `ReportBatchItemFailures` | The handler returns the IDs of the records it could not finish. The others are not repeated. |
| `destination_config.on_failure` | a standard SQS queue, `mofongo-dev-matcher-failed` | Records that are given up on leave a note here: which shard and which sequence numbers. The note does not hold the record itself. Alarm on this queue being non-empty. |

**Replay step for skipped records.** Do it within 24 hours, while the stream still has the records. Fix the cause first. Read the shard ID and sequence numbers from the queue message. Fetch the records with `GetShardIterator` (`AT_SEQUENCE_NUMBER`) and `GetRecords`, and run the matcher code on them. Running a record twice is safe because of the Matches check (section 6.7).

### 6.3 The score

A pair gets four parts. The total is 0 to 100.

| Part | Max | Rule |
|---|---|---|
| `category` | 40 | Both sides have the same category. The queries only return candidates in the same category, so every candidate gets all 40. |
| `colors` | 30 | 30 x (colors the two sides share) / (the smaller of the two color counts), rounded. |
| `clipCategory` | 15 | The item's CLIP score for the report's category (0 if it is not in the item's top 3), times 15 / 100, rounded. |
| `clipColor` | 15 | The best CLIP score the item has for any color on the report (0 if none is in its top 3), times 15 / 100, rounded. |

**Threshold:** a pair with a score of 60 or more is a match. The threshold is the environment variable `MATCH_THRESHOLD`, default 60.

Worked examples:
- Report: `water-bottle`, black. Item: `water-bottle`, black and green. CLIP: water-bottle 81, black 62. Score: 40 + 30 + 12 + 9 = 91. Match.
- Same report. The finder picked gray, not black. CLIP: water-bottle 81, black 55. Score: 40 + 0 + 12 + 8 = 60. Match. CLIP covered the color mix-up.
- Report: `water-bottle`, red. Item as in the first example. Score: 40 + 0 + 12 + 0 = 52. No match.

The weights and the threshold are a first guess. Tune them in week 6 with real photos. Keep them as named constants in one place in the matching Lambda. Every Match stores its `scoreParts`, so a score can always be explained.

The `why` lines come from the same parts. Add a line only for a part that scored:
- "Same category: {label}"
- "Shared color: {color}" (one line listing all shared colors)
- "The photo looks like {CLIP phrase} ({score}%)"
- "The photo looks {color} ({score}%)"

### 6.4 Direction A: an item gets its tags, check open reports

1. **Trigger:** the Items filter (section 6.2). The stream record's `NewImage` holds the whole item, including `clipTags`. No read is needed. `NewImage` is in DynamoDB JSON (for example `{"N": "81"}`), so convert it first with `boto3.dynamodb.types.TypeDeserializer`. Numbers then come back as `Decimal`.
2. **Candidates:** AP17. Query OpenByCategory with `openCategory` = the item's `category`. Each result carries `ownerId`, `reportId` and `colors`. Follow the pages, newest first, and stop at 500.
3. **Score** each report against the item (section 6.3).
4. **For each score at or above the threshold,** run "record and notify" (section 6.7) with that report's `ownerId`.

### 6.5 Direction B: a report is filed, check listed items

1. **Trigger:** the Reports filter. The `NewImage` holds the whole report. Convert it with `TypeDeserializer` first, as in section 6.4.
2. **Candidates:** AP18. Query ListedByCategory with `listedCategory` = the report's `category`. Follow the pages, newest first, and stop at 500.
3. **Look at each item's `tagStatus` in the result:**
   - `TAGGED`: use the index copy.
   - `PENDING`: the index may be a moment behind the table, so read the item once with AP3 (`ConsistentRead=true`). If it is `TAGGED` now, use it. If not, skip it. Direction A picks the pair up when the tags arrive.
   - `FAILED`: skip it.
4. **Score** each item against the report, then run "record and notify" for the matches. The owner is the new report's `ownerId`.

### 6.6 SNS: subscribing and publishing

There is one SNS topic, a standard topic (email subscriptions do not work on FIFO topics).

**Subscribing** happens in the API Lambda, in `POST /reports` when Users has no row for the caller, and in `POST /me/alerts`:

```python
resp = sns.subscribe(
    TopicArn=TOPIC_ARN,
    Protocol="email",
    Endpoint=email,                      # the ID token's email claim
    Attributes={"FilterPolicy": json.dumps({"ownerId": [user_id]})},
    ReturnSubscriptionArn=True,
)
arn = resp["SubscriptionArn"]            # a real ARN even before the owner confirms
```

Then the API saves `userId`, `arn` and the time with AP20.

- Only subscribe if the token's `email_verified` is true. In the HTTP API event the claims arrive as text, so compare with the string `"true"`. Check this with a real token in week 3.
- The filter policy goes inside the `Subscribe` call. A subscription without a filter receives every message on the topic. This way there is never a moment without one.
- A change to a filter policy takes up to 15 minutes to apply. We never change one after creation.
- The owner has 48 hours to click "Confirm subscription". After that SNS deletes the subscription.
- Subscribing the same address again with the same filter should give back the existing subscription. Confirm that in week 3 before relying on it.

**`GET /me/alerts`** reads the saved ARN (AP19) and calls `GetSubscriptionAttributes`:
- No Users row: `NONE`.
- `PendingConfirmation` is `"true"`: `UNCONFIRMED`.
- `PendingConfirmation` is `"false"`: `CONFIRMED`.
- SNS answers "not found": `GONE`.

**`POST /me/alerts`** runs the `Subscribe` call above again, saves the new ARN (AP20), then reads the state back the same way as `GET /me/alerts`:
- No `email` claim, or `email_verified` is not true: HTTP 403. Nothing is saved.
- SNS refuses the subscription (see section 8.5): HTTP 503. Nothing is saved.
- Otherwise: HTTP 200 with the state, usually `UNCONFIRMED`.

**Publishing** happens in the matching Lambda (section 6.7). Every message carries the owner's ID as a message attribute. SNS delivers it only to subscriptions whose filter policy lists that value. An owner who has not confirmed gets nothing, but the match is still saved and shows on the report detail screen.

### 6.7 Record and notify, never twice

Run these steps for every pair at or above the threshold:

1. **Record the pair (AP14).** A `PutItem` into Matches with the condition `attribute_not_exists(reportId)`. If DynamoDB answers `ConditionalCheckFailedException`, the pair was recorded before. Stop. Send nothing.
2. **Publish to SNS** with the owner's ID as the message attribute `ownerId`.
   - If SNS clearly refuses (a `ClientError`, such as `AuthorizationError`, `Throttling` or `InternalError`), or the request never reached SNS (any other SDK error, such as `ParamValidationError`, `NoCredentialsError`, `ConnectTimeoutError` or `EndpointConnectionError`), delete the row you just wrote (AP16) and report the stream record as failed (the handler returns it in `batchItemFailures`), so it is retried and the pair is recorded and sent again.
   - If the request reached SNS but the answer was lost (`ReadTimeoutError` or `ConnectionClosedError`), SNS may have accepted the message already. Keep the row, log it, and do not retry. This is treated like the "Lambda died after step 1" case below.
3. **Mark it emailed (AP15).** Set `notifiedAt`. If this write fails, only log it. The email has already gone.

```python
from botocore.exceptions import BotoCoreError, ClientError, ConnectionClosedError, ReadTimeoutError

try:
    matches.put_item(
        Item={"reportId": rid, "itemId": iid, "score": score,
              "scoreParts": parts, "why": why, "createdAt": now},
        ConditionExpression="attribute_not_exists(reportId)",
    )
except ClientError as e:
    if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
        return                           # already recorded: never email it twice
    raise

try:
    sns.publish(
        TopicArn=TOPIC_ARN,
        Subject="Mofongo: a found item may match your report",
        Message=f"Open {SITE_URL}/reports/{rid} to see it.",
        MessageAttributes={"ownerId": {"DataType": "String", "StringValue": owner_id}},
    )
except (ReadTimeoutError, ConnectionClosedError):  # reached SNS, answer lost: it may have sent it
    log.warning("publish result unknown for %s %s", rid, iid)
    return                               # keep the row, do not retry
except (ClientError, BotoCoreError):     # SNS refused, or the request never reached SNS
    matches.delete_item(Key={"reportId": rid, "itemId": iid},
                        ConditionExpression="attribute_not_exists(notifiedAt)")
    raise                                # the handler reports this record as failed

matches.update_item(
    Key={"reportId": rid, "itemId": iid},
    UpdateExpression="SET notifiedAt = :now",
    ConditionExpression="attribute_exists(reportId)",
    ExpressionAttributeValues={":now": now},
)
```

What this guarantees, and what it does not:
- The same pair is recorded once, even when a stream record arrives twice or both directions find the pair at the same moment. Only one `PutItem` can succeed. The stream retry never sends a second email for it.
- One rare case can still send a second email: the SDK itself retries a `Publish` that timed out after SNS had already accepted it.
- If SNS refuses, the pair is retried up to 3 times (section 6.2). After that the row is already deleted, so the pair is not saved and does not show on the report screen. A note lands in `mofongo-dev-matcher-failed`. Use the replay step in section 6.2.
- Two rare cases lose an email: the Lambda dies (for example a timeout) after step 1 and before step 2, or the publish times out. The match is saved, `notifiedAt` stays empty, and the owner still sees the match on the report detail screen. A row with no `notifiedAt` after a few minutes means that happened.
- The email body only holds a link. The match details stay in the app.

### 6.8 Races

- **Both directions at once.** An item gets its tags just as a matching report is filed. Both runs find the pair. The conditional `PutItem` lets one of them through.
- **Neither direction finds it.** If the report is filed first, direction A finds it when the item is tagged. If the item is tagged first, direction B finds it when the report arrives, and it reads `PENDING` items straight from the table. The remaining gap is a report filed within a fraction of a second of the tagging, while both indexes are behind. Stream delivery is usually slower than an index update, so this is very unlikely. If it ever shows up, a nightly check of open reports against listed items can be added.
- **A just-returned item.** The index can show it for a moment after it was marked returned. A match may be recorded for it. The report detail screen shows the item as `RETURNED`.
- **A just-closed report.** OpenByCategory can still list a report for a moment after it was closed, and a retried Reports stream record still shows the report as `OPEN`. So a match can still be recorded and emailed in the first seconds after closing, or later if a record is retried. This is rare and does no harm beyond one extra email. If it becomes a problem, read the report with `GetItem` and `ConsistentRead=true` before AP14 and skip it if it is `CLOSED`.

## 7. Traceability

### 7.1 Screen to endpoint

| Screen | Endpoints |
|---|---|
| 1.1 Browse items | `GET /items` |
| 1.2 Item detail | `GET /items/{itemId}`, `POST /items/{itemId}/returned` |
| 1.3 Post item | `POST /items` (the photo then goes straight to S3) |
| 1.4 File a lost report | `POST /reports` |
| 1.5 My reports | `GET /reports`, `GET /me/alerts` (banner) |
| 1.6 Report detail | `GET /reports/{reportId}`, `POST /reports/{reportId}/closed` (added) |
| 1.7 Email alert status | `GET /me/alerts`, `POST /me/alerts` (added) |

### 7.2 Endpoint to access pattern

| Caller | Access patterns | Other calls |
|---|---|---|
| `GET /items` | AP1 (all), AP2 (with `category`) | S3 presigned GET links |
| `POST /items` | AP4 | S3 presigned POST |
| `GET /items/{itemId}` | AP3 | S3 presigned GET link |
| `POST /items/{itemId}/returned` | AP7 | S3 presigned GET link |
| `POST /reports` | AP9, AP19, AP20 | SNS `Subscribe` |
| `GET /reports` | AP10 | none |
| `GET /reports/{reportId}` | AP11, AP13, AP8 | S3 presigned GET links |
| `POST /reports/{reportId}/closed` (added) | AP12 | none |
| `GET /me/alerts` | AP19 | SNS `GetSubscriptionAttributes` |
| `POST /me/alerts` (added) | AP20 | SNS `Subscribe`, then `GetSubscriptionAttributes` |
| Tagger (EC2) | AP5, AP6 | SQS, S3 |
| Matching Lambda | AP17, AP18, AP3, AP14, AP15, AP16 | SNS `Publish` |

### 7.3 Access pattern to key or index

| # | Table | Key or index |
|---|---|---|
| AP1 | Items | ListedByDate (`listedPk` + `createdAt`) |
| AP2 | Items | ListedByCategory (`listedCategory` + `createdAt`) |
| AP3 | Items | table key `itemId` |
| AP4 | Items | table key `itemId` |
| AP5 | Items | table key `itemId` |
| AP6 | Items | table key `itemId` |
| AP7 | Items | table key `itemId` |
| AP8 | Items | table key `itemId` |
| AP9 | Reports | table key `ownerId` + `reportId` |
| AP10 | Reports | ByOwner (`ownerId` + `createdAt`) |
| AP11 | Reports | table key `ownerId` + `reportId` |
| AP12 | Reports | table key `ownerId` + `reportId` |
| AP13 | Matches | table key, partition `reportId` |
| AP14 | Matches | table key `reportId` + `itemId` |
| AP15 | Matches | table key `reportId` + `itemId` |
| AP16 | Matches | table key `reportId` + `itemId` |
| AP17 | Reports | OpenByCategory (`openCategory` + `createdAt`) |
| AP18 | Items | ListedByCategory (`listedCategory` + `createdAt`) |
| AP19 | Users | table key `userId` |
| AP20 | Users | table key `userId` |

Result: every screen has an endpoint, every endpoint has an access pattern, and every access pattern uses a table key or an index. There is no Scan and no `FilterExpression`. Every index is used: ListedByDate by AP1, ListedByCategory by AP2 and AP18, ByOwner by AP10, OpenByCategory by AP17.

## 8. Limits and notes

### 8.1 Assumed traffic

These are guesses for a campus of about 500 active users, for a busy day. Correct them when real numbers exist.

| Pattern group | Per day | Busiest moment |
|---|---|---|
| Browse (AP1, AP2) | 1,000 page loads | about 2 a second |
| Item detail (AP3) | 500 | about 1 a second |
| Post an item and tag it (AP4, AP5, AP6) | 30 | well under 1 a second |
| Reports (AP9 to AP13, AP19, AP20) | 100 | well under 1 a second |
| Matching (AP14 to AP18) | about 50 runs | a few at once |

All of this is far below any DynamoDB limit. On-demand billing suits it, since there is nothing to size. This document does not estimate cost.

### 8.2 The single `LISTED` partition

ListedByDate uses one partition key value, `LISTED`, for every listed item. DynamoDB keeps all entries with the same key value together, and one key value takes roughly 1,000 writes and 3,000 read units a second. Each item writes this index about three times in its life (posted, tagged, returned), and every browse reads it.

At campus scale that is a few writes an hour. It would start to matter at several hundred new items a second, or about 1,000 browse page loads a second held for a long time. A campus will not come near that.

If it ever does, spread the key over a few values (`LISTED#0` to `LISTED#9`, picked at random when the item is posted), query all of them and merge the results by `createdAt`. Changing an index key means creating a new index and dropping the old one, so it is a planned change, not an edit. ListedByCategory is already spread over 14 key values.

### 8.3 Index reads are eventually consistent

- Index entries usually appear within a fraction of a second, but you cannot ask for a strongly consistent index read.
- A new item or report can be missing from a list for a moment after it is posted. A returned item can still show for a moment.
- The `POST` answers return the new record. The web app puts it at the top of the list itself instead of reloading.
- The base-table `GetItem` calls are strongly consistent, so opening a record right after posting it works.
- The matching Lambda re-reads `PENDING` items from the table (section 6.5) for this reason.

### 8.4 Item size

One DynamoDB item can be at most 400 KB, counting attribute names and values. The 1 MB figure you may see is the size of one `Query` page, not an item. These items are far below the limit.

| Table | Typical size | Largest realistic | Basis |
|---|---|---|---|
| Items | about 1 KB | about 2 KB | A guess. A 1000-character description plus `clipTags` of about 200 bytes. |
| Reports | about 0.7 KB | about 1.5 KB | A guess. |
| Matches | about 0.5 KB | about 0.8 KB | A guess. |
| Users | about 0.2 KB | about 0.2 KB | The ARN is about 100 bytes. |

Correct these if the real rows are very different.

### 8.5 SNS limits

- **200 filter policies per topic** by default (10,000 per project). Each owner with alerts uses one. The 201st `Subscribe` call fails with `FilterPolicyLimitExceeded` (HTTP 403). The API then still files the report and answers `alerts: "unavailable"`. `POST /me/alerts` answers HTTP 503. A quota increase fixes it, through Service Quotas.
- **Security risk: the 200 can be used up on purpose.** Anyone who signs up with a few hundred throwaway verified addresses can fill the topic, and then no real owner can turn on alerts.
  - **Accepted (Owen, 21 Oct 2026):** self sign-up stays open to any email address, so people outside campus can use the app. This risk and the fake `wallet-id` report gap in 8.7 are known and accepted.
  - Add an alarm on the topic's subscription count in week 3, so abuse is noticed.
  - If it happens, the fixes are a Cognito pre sign-up trigger that limits sign-up to the campus email domain, or turning off self sign-up.
- **15 minutes** for a filter policy change to apply.
- **48 hours** to confirm a subscription. After that SNS deletes it, and the state becomes `GONE`.
- **Bounces:** if an address bounces, SNS stops sending to it for 7 days.
- **Standard topics only** for email subscriptions.

### 8.6 Deletion protection and point-in-time recovery in dev

- **Point-in-time recovery: on for all four tables.** It keeps 35 days of history, and the data is tiny, so it costs very little. It protects against a bad deploy or a bad matching run. Matches matters most: it is the memory of which pairs were emailed, and losing it could send old emails again.
- **Deletion protection: on for all four tables,** from the first `terraform apply`. It costs nothing and stops `DeleteTable` from any source, including `terraform destroy` and a Terraform change that would replace a table.
- **To remove the stack on purpose:** make the setting a variable (for example `dynamodb_deletion_protection`, default true). Set it to false, run `terraform apply`, then destroy.
- **Changing a table's primary key** replaces the table. Turn protection off first, and know that the data is lost. This is why the keys are decided here, before any table exists. Adding or removing an index is an in-place change and needs no such step.
- **Terraform names:** `deletion_protection_enabled` and `point_in_time_recovery { enabled = true }` on `aws_dynamodb_table`.
- `force_destroy` is for buckets only. It does nothing for DynamoDB.

### 8.7 Known gaps

- **Wrong category.** The finder picks the category, and matching only compares an item and a report in the same category. If the two pick different categories, the pair is never compared. CLIP's guess is stored in `clipTags` and could widen the search later.
- **Photo never uploaded.** The item stays `PENDING`. It shows in Browse but is never matched. A cleanup is not built yet.
- **Tagging failed.** The item shows in Browse and is not matched. To retry, set `tagStatus` back to `PENDING` and queue the photo again. The next change to `TAGGED` starts matching.
- **The tagger is off at night and on weekends** (the weekday schedule). Items posted then wait as `PENDING`. Set the photo queue's message retention to 7 days. The default is 4 days, which a long weekend can pass. Set its dead-letter queue to 14 days (the maximum): a message keeps its first enqueue time when it moves, so the dead-letter queue must keep messages longer than the main queue.
- **`wallet-id` photos.** Browse hides them from everyone but the finder, but anyone can file a `wallet-id` report with a matching color and see matched photos on the report screen. Finders should not photograph the front of a card.
- **"Emailed" means handed to SNS,** not delivered. An owner who has not confirmed gets nothing, but still sees matches in the app.
- **No list of the finder's own items.** See section 1.
- **Email changes.** If a user changes their email in Cognito, the saved subscription still points at the old address. Not handled.
- **Duplicate posts.** A double tap on submit can create two items or two reports. The web app should disable the button after one click.
- **Matches shown:** the report detail screen shows up to 100 matches. A campus will not reach that.

### 8.8 Where this design differs from the DynamoDB method

| The method says | This design | Why |
|---|---|---|
| Protect retried `POST` routes with an idempotency table | No such table | A double tap makes one extra item or report. It does no harm, and the button is disabled after one click. |
| Use strongly consistent reads only where needed | Every `GetItem` is strongly consistent | After a `POST`, the next screen reads the new record. At this size the extra cost is nothing. |
| Project only what a pattern reads | `ALL` on all four indexes | A projection cannot change later, rows are small, and the score may need other attributes. |
| Prefer multi-attribute index keys | One-attribute sparse keys (`listedPk`, `listedCategory`, `openCategory`) | "Present or absent" is the simplest rule for a beginner. |
| Key tables by the authorization boundary | Reports, Users: yes. Items: keyed by `itemId`. Matches: keyed by `reportId`. | Items are public to signed-in users. Matches are reachable only after the report check (section 4). |
| Use `TransactWriteItems` for multi-row writes | Not used | No request writes more than one row. |

## Sources checked

AWS documentation, read on 21 Oct 2026:
- Lambda filtering for DynamoDB: https://docs.aws.amazon.com/lambda/latest/dg/with-ddb-filtering.html
- Lambda filter rule syntax and limits: https://docs.aws.amazon.com/lambda/latest/dg/invocation-eventfiltering.html
- DynamoDB tutorial on Lambda filters: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Streams.Lambda.Tutorial2.html
- Lambda settings for DynamoDB mappings: https://docs.aws.amazon.com/lambda/latest/dg/services-ddb-params.html
- SNS `Subscribe` (`ReturnSubscriptionArn`, `FilterPolicy`, errors): https://docs.aws.amazon.com/sns/latest/api/API_Subscribe.html
- SNS filter policy limits (200 per topic): https://docs.aws.amazon.com/sns/latest/dg/subscription-filter-policy-constraints.html
- SNS filter policies (15 minutes to apply): https://docs.aws.amazon.com/sns/latest/dg/sns-subscription-filter-policies.html
- SNS email subscriptions (48 hours, standard topics, bounces): https://docs.aws.amazon.com/sns/latest/dg/sns-email-notifications.html
- SNS `GetSubscriptionAttributes` (`PendingConfirmation`): https://docs.aws.amazon.com/boto3/latest/reference/services/sns/client/get_subscription_attributes.html
- DynamoDB sparse indexes: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-indexes-general-sparse-indexes.html
- DynamoDB failed conditional writes (`ALL_OLD`): https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithItems.html
- DynamoDB `BatchGetItem` limits: https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_BatchGetItem.html
- Strongly consistent reads are not supported on global secondary indexes: https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Query.html
- Lambda error handling for DynamoDB streams (retries, splitting, on-failure destination): https://docs.aws.amazon.com/lambda/latest/dg/services-dynamodb-errors.html
- SQS dead-letter queue retention (original enqueue time): https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html
- HTTP API JWT authorizer: https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-jwt-authorizer.html

The item size limit (400 KB), the per-partition limits and the stream reader limit come from the AWS DynamoDB data-modeling skill (`amazon-dynamodb`, loaded through the AWS MCP Server).
