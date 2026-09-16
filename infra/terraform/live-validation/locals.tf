locals {
  common_tags = {
    Project   = var.project_tag
    Purpose   = "drift-control-validation"
    ManagedBy = "Terraform"
  }
}
