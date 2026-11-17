# Custom VPC for the tagger (ADR 0005). Public subnets hold only the NAT gateway; the tagger runs in a
# private subnet with no public IP.
#
# EGRESS: this is ADR 0005 option A, one NAT gateway. The tagger reaches the model host, PyPI, SSM and SQS
# through the NAT on first boot; S3 and DynamoDB use the free gateway endpoints on the private route table.
# Option B (endpoints only, no NAT) is the hardening path per ADR 0005: add interface endpoints for ssm,
# ssmmessages, ec2messages and sqs, vendor the model and wheels, delete the NAT gateway, and set
# allow_internet_egress = false on the tagger module.
module "vpc" {
  source = "../../modules/vpc"

  name_prefix = local.name_prefix
}
