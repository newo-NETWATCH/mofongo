# Photo queue (+ dead-letter queue) that the photos bucket notifies on upload. The queue policy lets S3 send
# only for this bucket in this project (aws:SourceArn + aws:SourceAccount).
module "photo_queue" {
  source = "../../modules/photo_queue"

  name_prefix       = local.name_prefix
  photos_bucket_arn = module.photos_bucket.bucket_arn
  account_id        = local.account_id

  # A message in the dead-letter queue means a photo could not be tagged: tell the owner.
  alarm_actions = [module.alerts_topic.topic_arn]
}

# S3 -> SQS: every new object under photos/ puts one message on the photo queue (data-model section 6.1).
# depends_on the queue module so the queue policy exists first; S3 validates the destination when this is
# created and rejects it otherwise. Only one aws_s3_bucket_notification may exist per bucket.
resource "aws_s3_bucket_notification" "photos" {
  bucket = module.photos_bucket.bucket_name

  queue {
    queue_arn     = module.photo_queue.queue_arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "photos/"
  }

  depends_on = [module.photo_queue]
}
