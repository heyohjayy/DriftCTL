terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

variable "aws_region" {
  description = "AWS Region in which to create this disposable DriftCTL example."
  type        = string
  default     = "us-east-1"
}

provider "aws" {
  region = var.aws_region
}

# This isolated VPC and unattached security group have no hourly AWS charge.
# Keep the security group closed: it has no ingress or egress rules.
resource "aws_vpc" "driftctl_example" {
  cidr_block           = "10.254.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name    = "driftctl-example-vpc"
    Project = "DriftCTLExample"
    Purpose = "read-only-drift-scan-demo"
  }
}

resource "aws_security_group" "driftctl_example" {
  name                   = "driftctl-example-closed-sg"
  description            = "Closed, unattached security group for a DriftCTL example"
  vpc_id                 = aws_vpc.driftctl_example.id
  revoke_rules_on_delete = true
  ingress                = []
  egress                 = []

  tags = {
    Name    = "driftctl-example-closed-sg"
    Project = "DriftCTLExample"
    Purpose = "read-only-drift-scan-demo"
  }
}

output "driftctl_example_vpc_id" {
  value = aws_vpc.driftctl_example.id
}

output "driftctl_example_security_group_id" {
  value = aws_security_group.driftctl_example.id
}
