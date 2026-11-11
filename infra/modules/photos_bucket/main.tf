# Private bucket for item photos. The app hands out short-lived presigned URLs; the
# bucket itself is never public.

resource "aws_s3_bucket" "photos" {
  bucket = "mofongo-dev-photos-${var.account_id}"

  # App data bucket in a dev stack: let `terraform destroy` empty and remove it.
  force_destroy = true
}

# Objects are always owned by the bucket owner and ACLs are disabled.
resource "aws_s3_bucket_ownership_controls" "photos" {
  bucket = aws_s3_bucket.photos.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "photos" {
  bucket = aws_s3_bucket.photos.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# SSE-S3 (AES256), so no KMS endpoint or key policy is needed.
resource "aws_s3_bucket_server_side_encryption_configuration" "photos" {
  bucket = aws_s3_bucket.photos.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Lets the browser upload a photo straight to S3 with a presigned POST.
# The API hands out a presigned POST form (multipart/form-data), not a PUT URL,
# so S3 must allow cross-origin POST or the browser upload is blocked.
resource "aws_s3_bucket_cors_configuration" "photos" {
  bucket = aws_s3_bucket.photos.id

  cors_rule {
    allowed_origins = [var.cors_origin]
    allowed_methods = ["POST"]
    allowed_headers = ["Content-Type"]
    max_age_seconds = 3000
  }
}

# Frees storage from abandoned uploads.
resource "aws_s3_bucket_lifecycle_configuration" "photos" {
  bucket = aws_s3_bucket.photos.id

  rule {
    id     = "abort-incomplete-multipart"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

# Refuses any request that is not over HTTPS.
resource "aws_s3_bucket_policy" "photos" {
  bucket = aws_s3_bucket.photos.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          aws_s3_bucket.photos.arn,
          "${aws_s3_bucket.photos.arn}/*",
        ]
        Condition = {
          Bool = { "aws:SecureTransport" = "false" }
        }
      },
    ]
  })

  # Apply the public-access block first, so the bucket is never briefly open.
  depends_on = [aws_s3_bucket_public_access_block.photos]
}
