variable "aws_region" {
  description = "AWS region for this non-production validation environment."
  type        = string
  default     = "eu-west-1"
}

variable "project_tag" {
  description = "Project tag value used to scope DriftCTL scans."
  type        = string
  default     = "Test"
}

variable "validation_prefix" {
  description = "Prefix for named validation resources."
  type        = string
  default     = "driftctl-sprint3"
}

variable "private_zone_name" {
  description = "Name for the private Route 53 hosted zone."
  type        = string
  default     = "driftctl-sprint3.internal"
}

variable "enable_ec2_validation_instance" {
  description = "Whether to create the optional Systems Manager-enabled EC2 fixture. This can incur EC2 charges."
  type        = bool
  default     = false
}

variable "ec2_instance_type" {
  description = "Instance type for the optional EC2 validation fixture."
  type        = string
  default     = "t3.micro"
}
