# Output types match the api_lambda module inputs exactly (object, not map), so a typo in a key
# fails at plan time.

output "table_names" {
  description = "Table names by role."
  value = {
    items   = aws_dynamodb_table.items.name
    reports = aws_dynamodb_table.reports.name
    matches = aws_dynamodb_table.matches.name
    users   = aws_dynamodb_table.users.name
  }
}

output "table_arns" {
  description = "Table ARNs by role."
  value = {
    items   = aws_dynamodb_table.items.arn
    reports = aws_dynamodb_table.reports.arn
    matches = aws_dynamodb_table.matches.arn
    users   = aws_dynamodb_table.users.arn
  }
}

output "index_names" {
  description = "Global secondary index names. The api_lambda module maps these to env vars: items.listed_by_date -> IDX_LISTED_BY_DATE, items.listed_by_category -> IDX_LISTED_BY_CATEGORY, reports.by_owner -> IDX_BY_OWNER, reports.open_by_category -> IDX_OPEN_BY_CATEGORY (matcher only)."
  value = {
    items = {
      listed_by_date     = local.index_names.items.listed_by_date
      listed_by_category = local.index_names.items.listed_by_category
    }
    reports = {
      open_by_category = local.index_names.reports.open_by_category
      by_owner         = local.index_names.reports.by_owner
    }
  }
}

output "stream_arns" {
  description = "Stream ARNs for Items and Reports, read later by the matcher's event source mappings."
  value = {
    items   = aws_dynamodb_table.items.stream_arn
    reports = aws_dynamodb_table.reports.stream_arn
  }
}
