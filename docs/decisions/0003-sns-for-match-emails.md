# 0003. SNS for match emails

Date: 2026-10-21
Status: Accepted

## Context

- When a match is found, the owner of the lost report must get an email.
- The earlier plan used Amazon SES. This week's design changed it to SNS, with the matching Lambda publishing the alert.
- The app has never emailed these owners. It knows only the email in their Cognito ID token.
- SES and SNS are both available on the Free plan.
- A new SES setup starts in a sandbox. In the sandbox it sends only to verified addresses and domains, at most 200 messages in 24 hours and 1 message per second. The sandbox is per Region, so us-east-2 needs its own production access.

## Decision

Use one SNS Standard topic in us-east-2. Direct email subscriptions work only on Standard topics.

| Step | What happens |
|---|---|
| 1 | An owner files a report. If Users has no row for the owner, the API Lambda reads `email` and `email_verified` from the ID token. It subscribes the address only if `email_verified` is true. |
| 2 | The Lambda calls Subscribe with the `email` protocol, a filter policy on the owner's user ID, and `ReturnSubscriptionArn` set to true. It saves the ARN in Users. |
| 3 | SNS sends a "Confirm subscription" email from AWS Notifications, usually from `no-reply@sns.amazonaws.com`. The owner has 48 hours to click it. After that SNS deletes the pending subscription. |
| 4 | The matching Lambda publishes the alert with the owner's user ID as a String message attribute. SNS delivers it only to the subscription whose filter matches. |
| 5 | `GET /me/alerts` reads the subscription status. "Not found" means it expired or the owner unsubscribed, so the app offers to subscribe again. |
| 6 | `POST /me/alerts` subscribes again (after `NONE` or `GONE`) or asks SNS to resend the confirmation (after `UNCONFIRMED`; confirm in week 3 that a repeat `Subscribe` does resend it). It saves the new ARN in Users. |

- Set the filter policy in the same Subscribe call that creates the subscription, never in a later call.
- The emails are plain text. The body cannot be customized. Every email has an unsubscribe link.

## Consequences

Easier:
- No sandbox, no sender domain to verify and no production-access request.
- The cost is about $0. The first 1,000 email deliveries each month are free. After that it is about $2 per 100,000 (SNS list price, which names no Region). Filtering on message attributes is free.
- `ReturnSubscriptionArn` gives the ARN at once, even while the subscription is pending.

Harder or riskier:
- **Privacy.** A subscription without a filter policy receives every message on the topic, which means every owner's alert. One subscription made without a filter would let that person read everyone's matches. Set the filter in the Subscribe call. Add a test that every subscription has a filter policy. Never subscribe addresses by hand in the console.
- **A pending subscription receives nothing.** A match found before the owner confirms is not emailed. If the matching Lambda has already written the pair to Matches, the conditional write blocks a second try. The matcher does not check the alert state. It records and publishes every match, and an unconfirmed owner sees it only on the report page (`docs/data-model.md` section 6.6, "Publishing", and section 8.7).
- Filter policy changes take up to 15 minutes to apply. Do not expect a fix to a filter to work at once.
- The default limit is 200 filter policies per topic (10,000 per project). That is about 200 owners with alerts until a higher limit is requested.
- The emails come from AWS Notifications, not from Mofongo, so owners may not recognize them.
- The unsubscribe link works with one click. Email security scanners sometimes open links and unsubscribe people by accident. The app handles this with the "not found" case in step 5.
- A bounced address is blocked for 7 days.
- Sending more than 10 messages per second to one email subscription suspends it. It goes back to "pending confirmation" for 30 days, then SNS deletes it unless the owner confirms again. One match email at a time will not come near this.
- The SNS docs say email delivery is meant for internal system alerts, not marketing messages. AWS guidance sends email to customers through SES. Expect to be asked why SNS was used.

When moving to SES would make sense:
- More than about 200 owners need alerts and a higher filter-policy limit is not wanted.
- The email must come from a Mofongo address, or needs HTML or custom wording.
- Bounce and complaint reports are needed.

Moving would mean: verify a sender in SES, request production access in us-east-2, store the owner's email in Users, and have the matching Lambda call SES directly. The Subscribe and filter-policy code would go away.

## Alternatives considered

| Option | Why not |
|---|---|
| Amazon SES | It is the service AWS recommends for email to customers. In the sandbox it sends only to verified addresses, so emailing unknown owners needs production access first, and a verified sender. Not chosen for the 8-week build. It is the next step if the limits above are reached. |

## Sources

Checked on 2026-10-21.

- SNS email subscriptions (48 hours, bounces, 10 per second and the 30-day suspension): https://docs.aws.amazon.com/sns/latest/dg/sns-email-notifications.html
- Subscribe API (`ReturnSubscriptionArn`, tokens valid two days): https://docs.aws.amazon.com/sns/latest/api/API_Subscribe.html
- Message filtering (no filter policy gets every message): https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering.html
- Filter policy limits (200 per topic, 15 minutes): https://docs.aws.amazon.com/sns/latest/dg/subscription-filter-policy-constraints.html and https://docs.aws.amazon.com/sns/latest/dg/sns-subscription-filter-policies.html
- Unsubscribe link and sender: https://repost.aws/knowledge-center/prevent-unsubscribe-all-sns-topic
- SNS prices and free tier: https://aws.amazon.com/sns/faqs/ and https://aws.amazon.com/sns/pricing/
- SES sandbox: https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html
- Free plan services: https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html
