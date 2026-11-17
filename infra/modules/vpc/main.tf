# The VPC for the CLIP tagger (ADR 0005, option A: a single NAT gateway).
#
#   public  subnets  10.0.1.0/24, 10.0.2.0/24   -> internet gateway. Hold only the NAT gateway.
#   private subnets  10.0.10.0/24, 10.0.11.0/24 -> NAT gateway. The tagger lives here, no public IP.
#
# Only the tagger runs in this VPC. The API and matcher Lambdas stay outside it; DynamoDB, S3 and
# SQS are IAM-gated and outside it too. There are no database subnets because there is no database.
#
# This module owns the network only. The tagger instance and its security group belong to the
# tagger module.
#
# Egress, option A: the tagger downloads the CLIP model (Hugging Face) and pip wheels (PyPI) on
# first boot, so the private route table sends 0.0.0.0/0 to ONE NAT gateway (single AZ, for cost).
# SSM and SQS also reach AWS through the NAT, so there are no interface endpoints here.
#
# Option B (the hardening path, ADR 0005): endpoints only, no NAT. To move to B, in one commit:
#   - delete aws_nat_gateway.this, aws_eip.nat and aws_route.private_default;
#   - add interface endpoints for ssm, ssmmessages, ec2messages and sqs in ONE private subnet
#     (the tagger's AZ), with an endpoint security group that allows 443 in from the tagger SG;
#   - vendor the model and wheels into S3 (reached through the free S3 gateway endpoint below), or
#     bake them into an AMI, and pin hashes.
# The gateway endpoints, flow logs and subnets stay as they are.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  # The zone letter becomes the subnet name suffix: us-east-2a -> a.
  az_suffixes = [for az in var.azs : substr(az, length(az) - 1, 1)]
}

# ---------------------------------------------------------------- vpc

resource "aws_vpc" "this" {
  cidr_block = var.vpc_cidr

  # Both on: the gateway endpoints and SSM name resolution need them.
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.name_prefix}-vpc"
  }
}

# The default security group allows all traffic between its members. Adopt it with NO rules so
# nothing can use it by accident. Every real group is created explicitly by its own module.
resource "aws_default_security_group" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-default-deny"
  }
}

# ---------------------------------------------------------------- subnets

# Public: hold only the NAT gateway. Nothing launched here gets a public IP automatically.
resource "aws_subnet" "public" {
  count = length(var.azs)

  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = false

  tags = {
    Name = "${var.name_prefix}-public-${local.az_suffixes[count.index]}"
    Tier = "public"
  }
}

# Private: the tagger. No public IP, ever.
resource "aws_subnet" "private" {
  count = length(var.azs)

  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.private_subnet_cidrs[count.index]
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = false

  tags = {
    Name = "${var.name_prefix}-private-${local.az_suffixes[count.index]}"
    Tier = "private"
  }
}

# ---------------------------------------------------------------- internet gateway and NAT

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-igw"
  }
}

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name = "${var.name_prefix}-nat-eip"
  }

  # The address needs the internet gateway attached before it can be associated.
  depends_on = [aws_internet_gateway.this]
}

# ONE NAT gateway, in the first public subnet (ADR 0005 option A). It is a single point of
# failure for its AZ and it is billed around the clock, including while the tagger is stopped.
# That is accepted for a batch tagger whose work waits in SQS. Private subnets in the other AZ
# reach it across AZs.
resource "aws_nat_gateway" "this" {
  allocation_id     = aws_eip.nat.id
  subnet_id         = aws_subnet.public[0].id
  connectivity_type = "public"

  tags = {
    Name = "${var.name_prefix}-nat"
  }

  depends_on = [aws_internet_gateway.this]
}

# ---------------------------------------------------------------- route tables

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-public-rt"
  }
}

resource "aws_route" "public_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count = length(var.azs)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# One private route table shared by both private subnets (one NAT, so one default route).
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.this.id

  tags = {
    Name = "${var.name_prefix}-private-rt"
  }
}

# Option A only. Option B deletes this route and the NAT.
resource "aws_route" "private_default" {
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this.id
}

resource "aws_route_table_association" "private" {
  count = length(var.azs)

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ---------------------------------------------------------------- gateway endpoints (free)

# S3 and DynamoDB traffic from the private subnets stays on the AWS network and skips the NAT
# (no NAT data-processing charge for photos). Each adds a prefix-list route to the private route
# table. Default endpoint policy (full access): the tagger role's IAM policy is what limits
# access, and a restrictive endpoint policy would also block the first-boot S3 downloads of
# option B.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = {
    Name = "${var.name_prefix}-s3-gw"
  }
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${data.aws_region.current.region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = {
    Name = "${var.name_prefix}-dynamodb-gw"
  }
}

# ---------------------------------------------------------------- flow logs

# Every connection the VPC accepts or rejects (ALL), to CloudWatch Logs. This is the detection
# layer for tagger egress that ADR 0005 relies on while the NAT allows 443 to any host. Short
# retention keeps the ingestion and storage cost down. The log group uses the CloudWatch default
# encryption; a customer-managed KMS key is left out to avoid a key policy for the logs service.
resource "aws_cloudwatch_log_group" "flow" {
  name              = "/aws/vpc/${var.name_prefix}-flow-logs"
  retention_in_days = var.flow_log_retention_days
}

data "aws_iam_policy_document" "flow_assume" {
  statement {
    sid     = "FlowLogsAssumesRole"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }

    # Confused deputy protection: only flow logs of this project may assume the role.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:ec2:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:vpc-flow-log/*"]
    }
  }
}

resource "aws_iam_role" "flow" {
  name               = "${var.name_prefix}-vpc-flow-logs"
  description        = "Lets VPC Flow Logs of ${var.name_prefix}-vpc write to its one CloudWatch log group."
  assume_role_policy = data.aws_iam_policy_document.flow_assume.json
}

# Write to the one log group this module owns, and nothing else. The AWS example policy also
# lists logs:DescribeLogGroups on "*", but flow logs to an existing group work without it.
data "aws_iam_policy_document" "flow" {
  statement {
    sid       = "WriteFlowLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
    resources = ["${aws_cloudwatch_log_group.flow.arn}:*"]
  }
}

resource "aws_iam_role_policy" "flow" {
  name   = "write-flow-logs"
  role   = aws_iam_role.flow.id
  policy = data.aws_iam_policy_document.flow.json
}

resource "aws_flow_log" "this" {
  vpc_id                   = aws_vpc.this.id
  traffic_type             = "ALL"
  log_destination_type     = "cloud-watch-logs"
  log_destination          = aws_cloudwatch_log_group.flow.arn
  iam_role_arn             = aws_iam_role.flow.arn
  max_aggregation_interval = 60

  tags = {
    Name = "${var.name_prefix}-flow-logs"
  }

  depends_on = [aws_iam_role_policy.flow]
}
