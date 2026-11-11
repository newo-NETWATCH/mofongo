# SNS topic that CloudWatch alarms publish to. Subscriptions are added by the caller.
# Not encrypted with the AWS-managed SNS key on purpose: CloudWatch alarms cannot publish
# to a topic encrypted with that key.

resource "aws_sns_topic" "alerts" {
  name = "mofongo-dev-alerts"
}
