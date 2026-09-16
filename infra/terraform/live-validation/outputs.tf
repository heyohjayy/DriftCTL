output "vpc_id" {
  description = "Validation VPC ID."
  value       = aws_vpc.validation.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs for optional application layers."
  value       = [aws_subnet.public_primary.id, aws_subnet.public_secondary.id]
}

output "private_subnet_ids" {
  description = "Private subnet IDs for optional application layers."
  value       = [aws_subnet.private_primary.id, aws_subnet.private_secondary.id]
}

output "private_hosted_zone_id" {
  description = "Private Route 53 hosted-zone ID."
  value       = aws_route53_zone.private.zone_id
}
