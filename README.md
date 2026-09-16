# Infrastructure Drift Control Platform (DriftCTL)

`driftctl` is a read-only Terraform drift-detection and remediation-planning tool for AWS. It helps teams identify and safely resolve Terraform state drift: the common situation where a Terraform-managed environment no longer matches the configuration that exists in AWS.

The tool compares Terraform's recorded expected state with live AWS inventory, identifies the difference, classifies its risk, recommends a safe next action, and records an append-only audit trail. It never runs `terraform apply`, changes Terraform state, or calls AWS mutation APIs.

## Platform Capabilities

| Capability | What it provides |
| --- | --- |
| Expected versus live comparison | Loads Terraform state through `terraform show -json`, collects supported AWS configuration through read-only APIs, and compares normalized resource snapshots. |
| Drift taxonomy | Classifies every finding as `missing`, `unmanaged`, or `modified`, so teams can distinguish deleted resources, AWS-only resources, and changed configuration. |
| Risk classification | Uses modular severity rules to classify findings as minor, moderate, severe, or critical. Public SSH, RDP, and all-port security-group exposure are treated as critical risks; public RDS exposure and weakened RDS encryption or deletion protection are treated as severe. |
| Reports and audit history | Produces a Markdown report grouped by resource category and severity, plus append-only JSONL audit events for each scan, finding, and recommendation. |
| Read-only AWS access | Uses a dedicated least-privilege AWS policy and only `Describe`, `List`, and `Get` collection APIs. The scanner observes and reports; it does not apply remediation. |
| Environment scoping | Supports repeatable `--tag KEY=VALUE` filters so a scan can focus on one environment without unrelated regional resources creating findings. |
| Current AWS coverage | EC2 instances, security groups and their inline or standalone Terraform rules, S3 bucket public-access and encryption controls, VPCs, subnets, internet gateways, NAT gateways, route tables, network ACLs, IAM roles and instance profiles, Application Load Balancers, target groups, listeners, listener rules, RDS DB instances, ECS clusters, task definitions and services, CloudWatch log groups, plus Route 53 hosted zones and records. Unsupported Terraform types are reported as collection diagnostics rather than misclassified as drift. |
| Extension model | Future AWS services will be added through the same adapter, collector, comparison, severity, reporting, and validation pattern. Each supported service is documented here when it becomes part of the tool. |
| Automation (planned) | Automated Jenkins and GitHub Actions workflows are planned, but are not included yet. When added, they will run scheduled and on-demand scans, retain reports and audit logs, and notify teams about critical drift. |

## How DriftCTL Is Used

DriftCTL has two ways of being used:

- **Manual Scanning:** Scenario: *(After a Terraform apply, during an investigation, or before an approved change, an engineer runs a read-only scan against the applied Terraform state and the corresponding AWS environment.)* DriftCTL reports supported differences inside the chosen tag scope. It can be used for production or non-production infrastructure when the team applies its normal access controls and change process. (See [Configure Read-Only AWS Access](docs/SETUP.md#configure-read-only-aws-access) and [Run a Live Scan With the Full Command](docs/SETUP.md#run-a-live-scan-with-the-full-command) for the production manual-scanning workflow.)

- **Scheduled Automation:** A Jenkins pipeline or GitHub Actions workflow runs the same read-only comparison on a team-defined schedule or on demand, retains reports and audit records, and notifies the team about critical findings via Slack. *(P.S. This automation feature is not implemented yet. It is planned as an additional way for teams to use the tool.)*

The optional controlled-validation sections in the setup guide document how this project verified real detection behavior in a non-production environment. They are not a third operating mode and are not required before using DriftCTL in production. In routine use, DriftCTL reports whatever supported drift already exists; it does not expect a team to create drift first.

> [!NOTE]
> DriftCTL reads applied Terraform state with `terraform show -json`. It does not run `terraform init`, `terraform plan`, `terraform apply`, or `terraform refresh`, and it does not call AWS APIs that create, update, or delete resources.

> [!NOTE]
> Current coverage boundaries: DriftCTL supports Application Load Balancers, but not Network or Gateway Load Balancers. It does not evaluate target registration or runtime target health. RDS coverage is limited to DB instances, not Aurora clusters. When the tool cannot determine a reliable impact for a difference, it reports `NOT ASSESSED` instead of overstating risk.

## Quick Start

The offline demonstration is the fastest way to see the tool work. It uses included fixture files that resemble Terraform state and boto3 responses, so it does not access an AWS account or require credentials.

Python 3.11 or later is required. After cloning, change into the repository directory before running these commands. They create a `.venv` folder in the current directory, so do not run them from your home directory unless the repository is there.

> [!NOTE]
> DriftCTL works from Windows, Linux, and macOS terminals. The commands below are Windows PowerShell examples. Bash and Zsh use a different virtual-environment activation command and Unix-style paths; equivalents appear where the syntax differs.

Create the isolated Python environment:

```powershell
python -m venv .venv
```

Windows PowerShell can block local activation scripts. Allow this activation script to run in the current PowerShell window only; this does not change your computer's permanent execution-policy setting:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Activate the environment in Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

In Bash or Zsh on Linux or macOS, activate the same environment with:

```bash
source .venv/bin/activate
```

Install the project and development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Run the offline scan using the command for your terminal. In Windows PowerShell:

```powershell
driftctl scan --expected examples\expected.json --live examples\live.json --report reports\offline-drift-report.md --audit audit\offline-events.jsonl
```

In Bash or Zsh on Linux or macOS:

```bash
driftctl scan --expected examples/expected.json --live examples/live.json --report reports/offline-drift-report.md --audit audit/offline-events.jsonl
```

The command writes a Markdown report and appends JSONL audit events. This credential-free workflow is useful for local evaluation, development, and CI.

For a complete step-by-step guide to using DriftCTL manually, including safe live AWS testing and evidence screenshots, read [the setup and usage guide](docs/SETUP.md).

## Learn More

- [Setup and usage guide](docs/SETUP.md): the complete manual workflow, from installation and offline evaluation to safe live AWS scans, controlled validation, cleanup, and troubleshooting.
- [Terraform infrastructure](infra/terraform/README.md): the version-controlled non-production infrastructure reference used for this project's controlled live validation.
- [Read-only IAM policy](infra/iam/driftctl-read-only-policy.json): the least-privilege AWS inspection policy used by the live-scan workflow. The setup guide explains how to apply it safely.
- [Architecture notes](docs/architecture.md): how Terraform state, read-only AWS collection, normalization, comparison, reporting, audit history, and remediation guidance fit together.
- [Evidence index](docs/screenshots/README.md): screenshots from the offline and controlled live-validation demonstrations.
