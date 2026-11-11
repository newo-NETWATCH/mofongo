data "aws_region" "current" {}

# Open self sign-up with email as the username (risk accepted, docs/data-model.md 8.5).
# username_attributes is fixed at creation; changing it replaces the pool.
resource "aws_cognito_user_pool" "this" {
  name                     = "${var.name_prefix}-users"
  user_pool_tier           = var.user_pool_tier
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  mfa_configuration        = "OFF" # dev only; TOTP is a later switch to OPTIONAL
  deletion_protection      = var.deletion_protection

  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = "0"
      max_length = "2048"
    }
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Cognito's default sender is capped at about 50 emails a day. Fine for dev.
  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  # Threat protection (audit mode) needs the PLUS plan, which is paid, so it is
  # not configured here. Revisit if the project moves to a paid plan.
}

# Public SPA client: no secret, SRP only for sign-in, authorization code + PKCE.
# Refresh token rotation is not enabled: it is incompatible with
# ALLOW_REFRESH_TOKEN_AUTH, which the Amplify client library uses.
resource "aws_cognito_user_pool_client" "web" {
  name         = "${var.name_prefix}-web"
  user_pool_id = aws_cognito_user_pool.this.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  access_token_validity  = var.token_minutes
  id_token_validity      = var.token_minutes
  refresh_token_validity = var.refresh_token_days

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  supported_identity_providers         = ["COGNITO"]
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  callback_urls                        = var.callback_urls
  logout_urls                          = var.logout_urls

  read_attributes  = ["email", "email_verified"]
  write_attributes = ["email"]
}

# Cognito prefix domain: no ACM certificate, so nothing needs us-east-1.
resource "aws_cognito_user_pool_domain" "this" {
  domain       = var.domain_prefix
  user_pool_id = aws_cognito_user_pool.this.id
}
