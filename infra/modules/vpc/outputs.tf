output "vpc_id" {
  description = "ID of the VPC."
  value       = aws_vpc.this.id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC."
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of the public subnets, in the order of var.azs. They hold only the NAT gateway."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets, in the order of var.azs. Launch the tagger in one of these."
  value       = aws_subnet.private[*].id
}

output "private_route_table_id" {
  description = "ID of the private route table (default route to the NAT gateway, plus the S3 and DynamoDB gateway endpoints)."
  value       = aws_route_table.private.id
}

output "public_route_table_id" {
  description = "ID of the public route table (default route to the internet gateway)."
  value       = aws_route_table.public.id
}

output "nat_gateway_id" {
  description = "ID of the single NAT gateway (option A). Option B deletes the NAT gateway."
  value       = aws_nat_gateway.this.id
}

output "nat_public_ip" {
  description = "Elastic IP of the NAT gateway. Every outbound connection from the private subnets comes from this address."
  value       = aws_eip.nat.public_ip
}

output "gateway_endpoint_ids" {
  description = "IDs of the S3 and DynamoDB gateway endpoints, by service."
  value = {
    s3       = aws_vpc_endpoint.s3.id
    dynamodb = aws_vpc_endpoint.dynamodb.id
  }
}

output "flow_log_group_name" {
  description = "CloudWatch log group that receives the VPC Flow Logs (all traffic). Put the outbound-volume alarm's metric filter on this group."
  value       = aws_cloudwatch_log_group.flow.name
}
