variable "aws_region" { type = string }
variable "vpc_id" { type = string }
variable "artifacts_bucket_name" { type = string }
variable "enable_sprint3_route53" {
  type    = bool
  default = false
}
variable "sprint3_route53_zone_name" {
  type    = string
  default = "driftctl-sprint3.invalid"
}
