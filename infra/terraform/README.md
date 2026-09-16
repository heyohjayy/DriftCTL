# Terraform Infrastructure

This directory contains Terraform source used alongside DriftCTL. The source is version controlled so readers can inspect the infrastructure patterns behind the project's live validation without receiving local Terraform state, saved plans, AWS credentials, or generated scan results.

## Folders

| Folder | Purpose |
| --- | --- |
| [`example-infrastructure/`](example-infrastructure/) | A small generic Terraform example that demonstrates supported resource shapes. It is not the deployed live-validation environment. |
| [`live-validation/`](live-validation/) | The sanitized Terraform reference configuration for the non-production AWS environment used to validate DriftCTL against live resources and controlled drift. |

`live-validation/` represents the retained shared foundation: a VPC, public and private subnets across two Availability Zones, an internet gateway, route tables, a private network ACL, a private Route 53 hosted zone, and an optional Systems Manager-enabled EC2 test instance. The previous NAT gateway, Application Load Balancer, and RDS layer was deliberately destroyed after its validation because those services can incur charges. Future cost-bearing validation layers must be added deliberately, validated, and removed when their work is complete.

> [!WARNING]
> Terraform state, `.tfvars` files, saved plans, provider caches, private keys, reports, and audit logs are intentionally excluded from Git. Do not commit AWS credentials, account-specific generated output, or personal network details.

## Using the Live-Validation Reference

The configuration is a starting point for a dedicated learning or non-production account. It is not a state migration for the original project environment. Copy or use the source in [`live-validation/`](live-validation/), set your own values in a local `terraform.tfvars` file, then review `terraform plan` before applying anything.

The default configuration creates the shared network foundation only. The optional EC2 fixture is disabled by default, and chargeable application infrastructure is not included. This keeps a fresh review from creating NAT, load-balancing, or database costs unexpectedly.

For the full manual validation workflow, including read-only AWS access, tag-scoped scans, controlled-drift tests, and cleanup guidance, see [the setup guide](../../docs/SETUP.md).
