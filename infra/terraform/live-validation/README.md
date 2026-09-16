# Live Validation Infrastructure

This Terraform configuration is the sanitized reference for the non-production AWS environment used to validate DriftCTL against real Terraform state and live AWS resources. It is intentionally separate from DriftCTL's Python source: Terraform declares the expected infrastructure, while DriftCTL later reads the applied state and compares it with AWS through read-only APIs.

## What It Creates

By default, this configuration creates the retained validation foundation:

- One VPC with two public and two private subnets across two Availability Zones.
- An internet gateway and public route table.
- A private route table with no default internet route.
- A private network ACL.
- A private Route 53 hosted zone and one A record.
- An IAM role and instance profile for an optional EC2 test fixture.

The EC2 fixture is disabled by default. It has no SSH key, no inbound rule, and uses AWS Systems Manager rather than a personal SSH rule when enabled.

The NAT gateway, Elastic IP, Application Load Balancer, target group, listener, and RDS DB instance used in the earlier application-infrastructure validation are deliberately absent. They were destroyed after validation to prevent ongoing charges.

> [!WARNING]
> This is non-production infrastructure. Review every `terraform plan` before applying it. NAT gateways, load balancers, databases, and running EC2 instances can incur charges. Add those layers only for short-lived validation and destroy them when finished.

## Start Safely

Run the following from this folder. The commands initialize Terraform and show a proposed plan, but do not create resources until you explicitly run `terraform apply` after reviewing the plan.

```powershell
Copy-Item .\terraform.tfvars.example .\terraform.tfvars
terraform init
terraform plan
```

The local `terraform.tfvars`, Terraform state, plans, and `.terraform` provider cache are ignored by Git. Do not place credentials or personal network values in committed files.

After applying the configuration, use the same `Project` tag value in the DriftCTL scan scope. The full manual workflow is in [the setup guide](../../../docs/SETUP.md).
