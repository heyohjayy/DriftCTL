# DriftCTL Architecture

DriftCTL is a local, read-only comparison engine. It compares the infrastructure Terraform says is applied with the corresponding configuration AWS reports now, then produces findings and evidence for a human decision. It does not provision, modify, or delete infrastructure.

## Design Goals

- **Read-only by default:** DriftCTL never runs Terraform mutation commands and uses AWS collection APIs only.
- **Provider-neutral comparison:** Terraform state and AWS API responses are transformed into the same internal resource model before comparison.
- **Explainable findings:** Every finding includes its drift type, changed values, severity, impact assessment, and a remediation recommendation.
- **Evidence-first operation:** Each scan writes a Markdown report and a hash-chained JSONL audit log.
- **Composable service coverage:** A new AWS resource type is added through focused Terraform adaptation, AWS collection, normalization, severity policy, tests, and validation evidence.

## Scan Pipeline

```text
Terraform configuration
        |
        v
terraform plan -> human review and approval -> terraform apply
                                                   |
                          +------------------------+------------------------+
                          |                                                 |
                          v                                                 v
             Terraform state (expected)                       Live AWS environment
                          |                                                 |
                          +------------------------+------------------------+
                                                   |
                                                   v
                                  DriftCTL scan coordinator (read-only)
                                                   |
                  +--------------------------------+--------------------------------+
                  |                                                                 |
                  v                                                                 v
     Terraform CLI loader: terraform show -json                    AWS collector: Describe/List/Get APIs
                  |                                                                 |
                  v                                                                 v
     Terraform-state adapter -> expected ResourceSnapshots     boto3 adapter -> live ResourceSnapshots
                  |                                                                 |
                  +--------------------------------+--------------------------------+
                                                   |
                                                   v
                             Tag-scope filtering and collection diagnostics
                                                   |
                                                   v
                        Drift detector: missing | unmanaged | modified differences
                                                   |
                                                   v
                        Severity, impact, explanation, and remediation policies
                                                   |
                          +------------------------+------------------------+
                          |                                                 |
                          v                                                 v
          Markdown report grouped by category and severity     Hash-chained JSONL audit history
                          |                                                 |
                          +------------------------+------------------------+
                                                   |
                                                   v
                              Human review and approved remediation
                        Terraform change or AWS correction; never automatic
```

Terraform remains the source of expected applied state. AWS remains the source of live configuration. DriftCTL is the independent read-only control point between them.

## Components

| Layer | Responsibility | Main modules |
| --- | --- | --- |
| CLI and configuration | Resolves `driftctl.toml` and command-line options, validates inputs, coordinates a scan, renders terminal output, and returns automation-friendly exit codes. | `cli.py`, `scan_config.py` |
| Expected-state loader | Executes `terraform show -json` in an initialized Terraform working directory, or reads an offline expected-inventory fixture. | `loaders/terraform_cli.py` |
| Live-inventory collector | Uses the configured AWS profile or assumed role to call supported read APIs and records collection limitations as diagnostics. | `collectors/aws.py` |
| Adapters | Convert raw Terraform state and boto3 responses into the provider-neutral snapshot model. | `adapters/terraform_state.py`, `adapters/boto3_snapshots.py`, service helpers |
| Scope filter | Applies optional `KEY=VALUE` tag scope consistently to expected and live snapshots. | `scoping.py` |
| Drift detector | Compares snapshots by stable identity and records missing, unmanaged, or modified differences. | `detector.py` |
| Policy and presentation | Assigns severity, assesses known impacts, explains the difference, and produces a conservative recommended next action. | `severity_rules.py`, `presentation.py` |
| Evidence writers | Render the terminal view and Markdown report, then verify and append the JSONL audit chain. | `reporting.py`, `audit.py` |

## Provider-Neutral Data Model

Adapters produce a `ResourceSnapshot` for each supported resource. A snapshot contains:

- a stable `ResourceIdentity`: provider, resource type, and name;
- a resource category such as Networking, Compute, IAM, Storage, or Database;
- normalized, comparison-relevant attributes;
- optional Terraform source-address and provider-managed metadata.

The detector compares snapshot identities first. It classifies a resource as:

| Drift type | Meaning |
| --- | --- |
| `missing` | Terraform expects the resource, but it was not found in the live inventory. |
| `unmanaged` | The live inventory contains an in-scope resource that Terraform does not manage. AWS-managed resources identified by the collector are excluded from this classification. |
| `modified` | Expected and live snapshots share an identity but differ in one or more normalized attributes. |

Normalizing both sources before comparison prevents provider-specific response shapes from leaking into the detection logic. It also keeps resource collection, comparison rules, and reporting policies independently testable.

## Classification and Recommendations

After the detector produces a finding, modular severity rules classify it as `minor`, `moderate`, `severe`, or `critical`. Presentation rules then provide:

- an explanation of the difference and its known consequence;
- security, cost, and availability impact assessments, or `NOT ASSESSED` when the evidence is insufficient;
- a recommendation that requires human review and approval;
- expected and live values for the changed attributes.

DriftCTL does not decide whether Terraform or AWS is correct. A detected difference may represent an accidental change, an urgent operational correction, or an intentional change that was not yet reflected in Terraform. The tool preserves that decision for the responsible team.

## Reports and Audit Evidence

Each completed scan writes two local artifacts:

- a Markdown report organized by category and severity, including scan totals, collection diagnostics, findings, impacts, and remediation guidance;
- a JSONL audit log with scan, diagnostic, finding, severity-decision, and remediation events.

Audit events are serialized canonically and linked by SHA-256 hashes. DriftCTL verifies the existing chain before appending new events; changed, reordered, or malformed retained events cause the scan to fail rather than silently extend untrusted evidence.

> [!IMPORTANT]
> The audit chain is tamper-evident only for the retained local file. A user with filesystem access can delete or replace the entire log. Teams that require stronger retention guarantees should archive reports and audit logs in an access-controlled external system, such as their CI artifact store or central logging platform.

## Read-Only Safety Boundary

The scan path does not run `terraform init`, `terraform plan`, `terraform apply`, `terraform destroy`, `terraform refresh`, or AWS mutation APIs. Terraform provisioning, remediation, and cleanup remain outside DriftCTL and must be performed separately through the team's approved change process and administrative identity.

The supplied [read-only IAM policy](../infra/iam/driftctl-read-only-policy.json) is scoped to the AWS read actions needed for currently supported collection. A team can additionally constrain collection by Region, AWS account, role assumption, and tag scope.

## Automation Boundary

Manual and automated runners invoke the same `driftctl scan` coordinator. The command returns:

| Exit code | Meaning |
| --- | --- |
| `0` | Scan completed with no findings, or no finding met the configured `--fail-on` threshold. |
| `2` | Drift was found, or a finding met the configured `--fail-on` threshold. |
| `1` | The scan could not complete, for example because configuration, Terraform state, AWS credentials, collection, or audit-chain verification failed. |

This contract allows Jenkins or GitHub Actions to archive the report and audit log, apply notification policy, and distinguish an operational finding from a failed scan. Automation does not change the scanner's read-only behavior or perform remediation.

## Extending AWS Coverage

Adding support for a resource type requires the following work as one unit:

1. Add Terraform-state adaptation to produce the expected snapshot.
2. Add only the AWS read collection required for the live snapshot.
3. Normalize both sides to stable identities and comparison-relevant attributes.
4. Add or extend severity, impact, explanation, and remediation rules.
5. Add focused unit tests and update the least-privilege IAM policy test.
6. Validate the path in a non-production environment and record sanitized evidence.

Unsupported Terraform types remain visible as collection diagnostics rather than being silently ignored or incorrectly reported as drift.

## Related Documentation

- [Usage Guide](USAGE.md): first-time and repeatable manual scans.
- [Linux Quick Walkthrough](LINUX_USAGE.md): a direct Ubuntu/Debian disposable-example path.
- [Controlled Validation Guide](VALIDATION.md): non-production validation procedures and evidence.
- [Read-only IAM policy](../infra/iam/driftctl-read-only-policy.json): AWS collection permissions for supported resources.
