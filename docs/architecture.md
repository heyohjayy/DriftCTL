# Architecture

This diagram is the end-to-end architecture for Infrastructure Drift Control. The scanner path is implemented today; the Jenkins, GitHub Actions, and broader-service collection paths show the intended operational model as the platform grows.

```text
DEPLOYMENT PATH: Terraform establishes the intended environment

 Terraform configuration                 Human review and approval
 (resources, tags, rules)                         |
            |                                     v
            +----------------------------> terraform plan
                                                   |
                                                   v
                                            terraform apply
                                                   |
                         +-------------------------+-------------------------+
                         |                                                   |
                         v                                                   v
              Terraform state file                              Live AWS environment
         (expected recorded state)                    (EC2, security groups, S3,
                         |                             and future AWS services)
                         |                                                   |
                         +-------------------------+-------------------------+
                                                   |
                                                   v

OBSERVATION PATH: DriftCTL compares intended and live state without changing either

 Manual engineer command                 Jenkins scheduled/manual job       GitHub Actions workflow
 driftctl scan ...                       (intended automation)              (intended additional runner)
            |                                      |                                      |
            +--------------------+-----------------+----------------------+---------------+
                                 |
                                 v
                         DriftCTL scan coordinator
                                 |
              +------------------+-------------------+
              |                                      |
              v                                      v
  Terraform CLI loader                     Read-only AWS collector
  terraform show -json                     profile or assumed role, region,
              |                             optional tag scope
              v                                      |
  Terraform-state adapter                           v
              |                              boto3 response adapter
              v                                      |
 Expected ResourceSnapshot inventory                  v
              |                              Live ResourceSnapshot inventory
              +----------------------+---------------+
                                     |
                                     v
               Tag-scope filtering and collection diagnostics
                                     |
                                     v
             Drift detector: missing | unmanaged | modified
                                     |
                                     v
          Ordered, composable severity policies
          minor | moderate | severe | critical
                                     |
                    +----------------+----------------+
                    |                                 |
                    v                                 v
     Markdown report by category and severity   Append-only JSONL audit log
                    |                                 |
                    +----------------+----------------+
                                     |
                                     v
                  Human review and approved remediation
                 (Terraform change or AWS correction, never auto-applied)
```

## How the Paths Work Together

`terraform apply` is deliberately outside DriftCTL. Terraform applies the approved configuration and records the resulting expected state. DriftCTL later reads that state through `terraform show -json` and independently collects the live AWS configuration. It does not deploy, modify, or repair infrastructure.

The manual CLI, Jenkins, and GitHub Actions are alternative entry points to the same scanner. A team can run `driftctl scan` directly during investigation, use Jenkins for scheduled monitoring and artifact retention, or use GitHub Actions as another CI runner. Each path must authenticate with a dedicated read-only AWS identity.

## Scanner Boundaries

The Terraform adapter and boto3 adapter convert source-specific input into common `ResourceSnapshot` objects. The detector compares only those normalized inventories, so Terraform state and boto3 dictionary details remain outside the comparison logic.

Terraform security-group rules can be declared inline or as separate ingress and egress rule resources. The Terraform adapter aggregates those rules into their parent security-group snapshot, while the boto3 adapter normalizes AWS `IpPermissions` and `IpPermissionsEgress` into the same canonical form before comparison.

Repeatable `--tag KEY=VALUE` options limit both inventories to one environment. The active scope and unsupported resource types become collection diagnostics in the report and audit log, so unsupported resources are never incorrectly reported as missing drift.

## Current and Intended Coverage

Current collection covers EC2 instances, security groups, and supported S3 controls through read-only AWS APIs. The same architecture is intended to extend to VPCs, subnets, route tables, availability zones, load balancers, Lambda functions, Route 53, and IAM configuration. Each service follows the same pattern: Terraform adapter, AWS collector, normalized comparison, severity policies, reporting, audit events, and live validation.

Remediation is always a recommendation for human review. The Markdown report groups findings by category and severity, while the JSONL audit log records scans, collection diagnostics, findings, and remediation decisions.
