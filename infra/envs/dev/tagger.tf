# Tagger: EC2 instance in the private subnet that pulls photo messages from SQS, scores each photo with
# zero-shot CLIP against the fixed CATEGORY and COLOR lists, and writes clipTags to the Items table
# (tagStatus PENDING -> TAGGED), which starts the matcher. docs/decisions/0004.
# Session Manager only: no SSH, no key pair. Runs on the weekday schedule to save credits.
module "tagger" {
  source = "../../modules/tagger"

  name_prefix = local.name_prefix

  vpc_id            = module.vpc.vpc_id
  private_subnet_id = module.vpc.private_subnet_ids[0]

  photo_queue_arn = module.photo_queue.queue_arn
  photo_queue_url = module.photo_queue.queue_url

  photos_bucket    = module.photos_bucket.bucket_name
  items_table_name = module.dynamodb.table_names.items
  items_table_arn  = module.dynamodb.table_arns.items

  # envs/dev -> repo root worker/. Zipped into user_data and unpacked on first boot.
  worker_dir        = abspath("${path.module}/../../../worker")
  worker_entrypoint = "worker.py"

  # Option A (default true): outbound 443 via the NAT gateway. See vpc.tf for the option B path.
  allow_internet_egress = true
}
