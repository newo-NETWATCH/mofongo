# The four DynamoDB tables, exactly as docs/data-model.md section 4 and 7.3 define them.
#
# Keys, index names, projections and stream settings are the design, not inputs: changing a
# primary key replaces the table and loses its data, so they are fixed here.
#
# Encryption: every DynamoDB table is encrypted at rest. With no server_side_encryption block
# the table uses an AWS-owned key (data-model section 4), which costs nothing and needs no KMS
# grants for the API or matcher roles.
#
# Sparse indexes are not a Terraform setting. listedPk, listedCategory and openCategory are
# simply absent from rows that should leave the index (data-model 4.1 and 4.2).

locals {
  table_names = {
    items   = "${var.name_prefix}-items"
    reports = "${var.name_prefix}-reports"
    matches = "${var.name_prefix}-matches"
    users   = "${var.name_prefix}-users"
  }

  # Fixed index names. Exposed through the index_names output so the Lambda environment and the
  # IAM policy never retype them.
  index_names = {
    items = {
      listed_by_date     = "ListedByDate"
      listed_by_category = "ListedByCategory"
    }
    reports = {
      open_by_category = "OpenByCategory"
      by_owner         = "ByOwner"
    }
  }
}

# Items: one row per found item. Key: itemId.
resource "aws_dynamodb_table" "items" {
  name         = local.table_names.items
  billing_mode = "PAY_PER_REQUEST"
  table_class  = "STANDARD"

  hash_key = "itemId"

  attribute {
    name = "itemId"
    type = "S"
  }
  attribute {
    name = "listedPk"
    type = "S"
  }
  attribute {
    name = "listedCategory"
    type = "S"
  }
  attribute {
    name = "createdAt"
    type = "S"
  }

  # AP1: browse newest first. Only rows with listedPk = "LISTED" are in the index.
  global_secondary_index {
    name = local.index_names.items.listed_by_date
    key_schema {
      attribute_name = "listedPk"
      key_type       = "HASH"
    }
    key_schema {
      attribute_name = "createdAt"
      key_type       = "RANGE"
    }
    projection_type = "ALL"
  }

  # AP2 and AP18: browse or match by category. Only rows with listedCategory are in the index.
  global_secondary_index {
    name = local.index_names.items.listed_by_category
    key_schema {
      attribute_name = "listedCategory"
      key_type       = "HASH"
    }
    key_schema {
      attribute_name = "createdAt"
      key_type       = "RANGE"
    }
    projection_type = "ALL"
  }

  # The matching Lambda reads this stream. The item filter needs OldImage (data-model 6.1).
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  deletion_protection_enabled = var.deletion_protection

  tags = merge(var.tags, { Name = local.table_names.items })
}

# Reports: one row per lost report. Key: ownerId + reportId, so the API builds every key from the
# token's sub and a caller cannot reach another owner's report (data-model 4.2).
resource "aws_dynamodb_table" "reports" {
  name         = local.table_names.reports
  billing_mode = "PAY_PER_REQUEST"
  table_class  = "STANDARD"

  hash_key  = "ownerId"
  range_key = "reportId"

  attribute {
    name = "ownerId"
    type = "S"
  }
  attribute {
    name = "reportId"
    type = "S"
  }
  attribute {
    name = "openCategory"
    type = "S"
  }
  attribute {
    name = "createdAt"
    type = "S"
  }

  # AP10: one owner's reports, newest first. Not sparse: every report has both keys.
  global_secondary_index {
    name = local.index_names.reports.by_owner
    key_schema {
      attribute_name = "ownerId"
      key_type       = "HASH"
    }
    key_schema {
      attribute_name = "createdAt"
      key_type       = "RANGE"
    }
    projection_type = "ALL"
  }

  # AP17: open reports by category, read by the matching Lambda only. Sparse on openCategory.
  global_secondary_index {
    name = local.index_names.reports.open_by_category
    key_schema {
      attribute_name = "openCategory"
      key_type       = "HASH"
    }
    key_schema {
      attribute_name = "createdAt"
      key_type       = "RANGE"
    }
    projection_type = "ALL"
  }

  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  deletion_protection_enabled = var.deletion_protection

  tags = merge(var.tags, { Name = local.table_names.reports })
}

# Matches: one row per matched report and item pair. Key: reportId + itemId. No index, no stream.
# Written only by the matching Lambda, read by the API after it has checked report ownership.
resource "aws_dynamodb_table" "matches" {
  name         = local.table_names.matches
  billing_mode = "PAY_PER_REQUEST"
  table_class  = "STANDARD"

  hash_key  = "reportId"
  range_key = "itemId"

  attribute {
    name = "reportId"
    type = "S"
  }
  attribute {
    name = "itemId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  deletion_protection_enabled = var.deletion_protection

  tags = merge(var.tags, { Name = local.table_names.matches })
}

# Users: one row per user, holding the email alert subscription. Key: userId. No index, no stream.
resource "aws_dynamodb_table" "users" {
  name         = local.table_names.users
  billing_mode = "PAY_PER_REQUEST"
  table_class  = "STANDARD"

  hash_key = "userId"

  attribute {
    name = "userId"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.point_in_time_recovery
  }

  deletion_protection_enabled = var.deletion_protection

  tags = merge(var.tags, { Name = local.table_names.users })
}
