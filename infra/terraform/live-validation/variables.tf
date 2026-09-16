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

variable "enable_ecs_fargate_validation" {
  description = "Whether to create the optional ECS on Fargate validation fixture. This incurs ECS and CloudWatch Logs charges while enabled."
  type        = bool
  default     = false
}

variable "ecs_desired_count" {
  description = "Number of tasks for the optional ECS on Fargate validation service."
  type        = number
  default     = 1
}
