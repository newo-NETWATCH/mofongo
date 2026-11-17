# Regional AWS WAF in front of the REST API. Scope is REGIONAL, so it lives in the
# selected Region (us-east-2). Nothing here needs us-east-1.

resource "aws_wafv2_web_acl" "api" {
  name        = var.name
  description = "Protects the Mofongo REST API stage."
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  # AWS-maintained rules for common web exploits (XSS, bad inputs, oversized bodies, ...).
  rule {
    name     = "aws-common-rule-set"
    priority = 10

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-common-rules"
      sampled_requests_enabled   = true
    }
  }

  # AWS-maintained rules for known-bad inputs and exploit signatures.
  rule {
    name     = "aws-known-bad-inputs"
    priority = 15

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-known-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  # Blocks one IP address that sends too many requests in 5 minutes.
  rule {
    name     = "rate-limit-per-ip"
    priority = 20

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit                 = var.rate_limit
        aggregate_key_type    = "IP"
        evaluation_window_sec = 300
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.name}-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = var.name
    sampled_requests_enabled   = true
  }
}

resource "aws_wafv2_web_acl_association" "api" {
  resource_arn = var.resource_arn
  web_acl_arn  = aws_wafv2_web_acl.api.arn
}
