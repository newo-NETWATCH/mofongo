# The tagger: one EC2 instance that polls the photo queue, tags each photo with zero-shot CLIP and
# writes the tags to the Items table, which starts the matcher (data-model 4.1, 6.1, 6.2).
# Spec: docs/decisions/0004-clip-on-ec2-with-sqs-pull.md and 0005-vpc-three-tier-network.md.
#
# EGRESS: this module is built for ADR 0005 OPTION A (single NAT gateway). The instance sits in a
# private subnet with no public IP. Its route table (owned by the VPC module, not here) sends
# 0.0.0.0/0 to the NAT gateway and holds the free S3 and DynamoDB gateway endpoints. SSM, SQS and
# CloudWatch Logs are reached over the NAT, so there are no interface endpoints in option A.
# OPTION B (endpoints only, no NAT) is the hardening path per ADR 0005: set
# allow_internet_egress = false, pass endpoint_security_group_id, add the ssm, ssmmessages,
# ec2messages, sqs (and logs) interface endpoints, and vendor the wheels and model into S3 or an AMI.
#
# Access is Session Manager only: no key pair, no port 22, no inbound rule of any kind.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

locals {
  instance_name = "${var.name_prefix}-tagger"
  log_group     = "/mofongo/${local.instance_name}"

  worker_entrypoint_path = "${var.worker_dir}/${var.worker_entrypoint}"

  # Latest Amazon Linux 2023 (x86_64, c7i-flex is Intel). AWS publishes this public SSM parameter.
  al2023_ssm_parameter = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"

  user_data = templatefile("${path.module}/bootstrap.sh.tftpl", {
    worker_zip_b64     = filebase64(data.archive_file.worker.output_path)
    worker_entrypoint  = var.worker_entrypoint
    torch_requirements = join(" ", [for r in var.torch_requirements : "'${r}'"])
    requirements_txt   = trimspace(var.requirements_txt)
    clip_model_sha256  = var.clip_model_sha256
    queue_url          = var.photo_queue_url
    photos_bucket      = var.photos_bucket
    items_table        = var.items_table_name
    region             = data.aws_region.current.region
    log_group          = local.log_group
  })

  # EC2 user data is limited to 16 KB AFTER gzip and before the provider's base64. base64gzip gives
  # 4/3 of that, so 21,000 characters is about 15.7 KB. Plan fails with a clear message beyond it.
  user_data_b64 = base64gzip(local.user_data)
}

# ---------------------------------------------------------------- worker bundle

# The zip holds the worker's source files only. The size check below keeps it inside user_data.
data "archive_file" "worker" {
  type        = "zip"
  source_dir  = var.worker_dir
  output_path = "${path.module}/.build/worker.zip"
  excludes    = ["__pycache__", ".pytest_cache", "tests", "test_*.py", "*.pyc", "README.md"]

  lifecycle {
    precondition {
      condition     = fileexists(local.worker_entrypoint_path)
      error_message = "worker_entrypoint ${var.worker_entrypoint} is not in ${var.worker_dir}. Write the worker first, or set worker_entrypoint to its real file name."
    }
  }
}

# ---------------------------------------------------------------- logs

# Terraform owns the log group, so the role needs no logs:CreateLogGroup. The agent config sets
# retention_in_days to -1, so it never tries to change the retention either.
resource "aws_cloudwatch_log_group" "tagger" {
  name              = local.log_group
  retention_in_days = var.log_retention_days
}

# ---------------------------------------------------------------- security group

# NO inbound rules. Session Manager opens its connection outward on 443, so nothing listens.
# With no egress rule at all the instance could reach nothing (a Terraform security group has no
# default allow-all egress), so each outbound path is an explicit rule below.
resource "aws_security_group" "tagger" {
  name        = "${local.instance_name}-sg"
  description = "Mofongo tagger: no inbound, outbound TCP 443 only"
  vpc_id      = var.vpc_id

  # Rules are separate resources (below). Inline ingress/egress blocks would fight them.
  revoke_rules_on_delete = false

  lifecycle {
    precondition {
      condition     = data.aws_region.current.region == "us-east-2"
      error_message = "The tagger module must run in us-east-2 (project rule: everything stays in us-east-2)."
    }
  }

  tags = {
    Name = "${local.instance_name}-sg"
  }
}

data "aws_prefix_list" "s3" {
  name = "com.amazonaws.${data.aws_region.current.region}.s3"
}

data "aws_prefix_list" "dynamodb" {
  name = "com.amazonaws.${data.aws_region.current.region}.dynamodb"
}

# Option A: SSM, SQS, CloudWatch Logs, PyPI, the PyTorch index and Hugging Face are all HTTPS on
# any address, through the NAT. This does NOT stop outbound command-and-control on 443; it only
# narrows the port. Flow Logs and the outbound-volume alarm detect it, and option B closes it.
resource "aws_vpc_security_group_egress_rule" "https_internet" {
  count = var.allow_internet_egress ? 1 : 0

  security_group_id = aws_security_group.tagger.id
  description       = "HTTPS to the internet through the NAT gateway (option A)"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

# Photos and tags go over the free gateway endpoints. These two rules are redundant while the
# rule above exists; they are what keeps S3 and DynamoDB working when it is removed (option B).
resource "aws_vpc_security_group_egress_rule" "s3" {
  security_group_id = aws_security_group.tagger.id
  description       = "HTTPS to S3 through the gateway endpoint"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  prefix_list_id    = data.aws_prefix_list.s3.id
}

resource "aws_vpc_security_group_egress_rule" "dynamodb" {
  security_group_id = aws_security_group.tagger.id
  description       = "HTTPS to DynamoDB through the gateway endpoint"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  prefix_list_id    = data.aws_prefix_list.dynamodb.id
}

# Option B: SSM, SQS and logs through the interface endpoints' security group.
resource "aws_vpc_security_group_egress_rule" "interface_endpoints" {
  count = var.endpoint_security_group_id == null ? 0 : 1

  security_group_id            = aws_security_group.tagger.id
  description                  = "HTTPS to the interface endpoints (option B)"
  ip_protocol                  = "tcp"
  from_port                    = 443
  to_port                      = 443
  referenced_security_group_id = var.endpoint_security_group_id
}

# ---------------------------------------------------------------- instance

data "aws_ssm_parameter" "al2023" {
  name = local.al2023_ssm_parameter
}

resource "aws_instance" "tagger" {
  ami           = data.aws_ssm_parameter.al2023.value
  instance_type = var.instance_type

  subnet_id                   = var.private_subnet_id
  vpc_security_group_ids      = [aws_security_group.tagger.id]
  associate_public_ip_address = false # private subnet, no public IP (ADR 0005)
  iam_instance_profile        = aws_iam_instance_profile.tagger.name
  # No key_name: Session Manager replaces SSH.

  # IMDSv2 only, so a request-forwarding bug cannot read the role credentials with a plain GET.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1 # no containers on this host
    instance_metadata_tags      = "disabled"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gb
    encrypted             = true
    delete_on_termination = true

    tags = {
      Name = "${local.instance_name}-root"
    }
  }

  # First-boot bootstrap (bootstrap.sh.tftpl). Changing the worker code or settings changes this
  # and REPLACES the instance, so the new code is installed by a clean first boot. A stop and
  # start never re-runs it.
  user_data_base64            = local.user_data_b64
  user_data_replace_on_change = true

  lifecycle {
    # The AMI parameter moves every few weeks. Do not replace a working tagger for it; replace it
    # on purpose with `terraform apply -replace=module.tagger.aws_instance.tagger`.
    ignore_changes = [ami]

    precondition {
      condition     = length(local.user_data_b64) <= 21000
      error_message = "The worker bundle makes user_data too large (EC2 limit 16 KB after gzip). Shrink worker_dir, or move the worker code to an S3 object and fetch it on boot."
    }
  }

  depends_on = [
    aws_iam_role_policy.tagger,
    aws_iam_role_policy_attachment.ssm_core,
    aws_cloudwatch_log_group.tagger,
  ]

  tags = {
    Name = local.instance_name
  }
}
