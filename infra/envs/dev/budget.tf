# Monthly cost alert.
#
# Check first for a budget made in the console:
#   aws budgets describe-budgets --account-id <account-id> --profile mofongo
#
# If one exists, either delete it in the Billing console, or bring it under
# Terraform: add the block below and change `name` further down to its exact
# existing name. Renaming a budget makes Terraform delete and recreate it.
#
#   import {
#     to = aws_budgets_budget.monthly
#     id = "<account-id>:<exact existing name>"
#   }
#
# Do not use `terraform plan -generate-config-out` here: this file already
# holds the resource.

resource "aws_budgets_budget" "monthly" {
  name         = "mofongo-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # By default a budget subtracts AWS credits, so it reads $0 while credits pay
  # for everything. Counting usage before credits makes the alert fire on real use.
  cost_types {
    include_credit = false
  }

  # Email when actual spend passes 80% of the limit.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  # Email when AWS forecasts the month will end over the limit.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
