module "photos_bucket" {
  source = "../../modules/photos_bucket"

  account_id  = local.account_id
  cors_origin = var.cors_origin
}
