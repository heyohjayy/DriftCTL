variable "aws_region" { type = string }
variable "vpc_id" { type = string }
variable "artifacts_bucket_name" { type = string }
variable "enable_validation_route53" {
  type    = bool
  default = false
}
variable "validation_route53_zone_name" {
  type    = string
  default = "driftctl-validation.invalid"
}
