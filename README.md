<h1 align="center">
  <img src="assets/driftctl-logo.png" alt="DriftCTL alignment mark" height="82" valign="middle">
  <img src="assets/driftctl-wordmark-gradient.svg" alt="DriftCTL" height="82" valign="middle">
</h1>

<p align="center"><strong>Infrastructure Drift Control Platform</strong></p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11 or later"></a>
  <a href="https://www.terraform.io/"><img src="https://img.shields.io/badge/Terraform-State-7B42BC?logo=terraform&logoColor=white" alt="Terraform state"></a>
  <a href="https://aws.amazon.com/"><img src="https://img.shields.io/badge/AWS-Read--only%20collection-232F3E?logo=amazonaws&logoColor=white" alt="Read-only AWS collection"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-AGPL--3.0-D22128" alt="GNU Affero General Public License v3.0"></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/Contributions-Welcome-2EA44F" alt="Contributions welcome"></a>
</p>

<p align="center"><strong>Detect Terraform-to-AWS drift before it becomes operational debt.</strong></p>

`DriftCTL` is a read-only Terraform drift-detection and remediation-planning tool for AWS. It helps teams identify and safely resolve Terraform state drift: the common situation where a Terraform-managed environment no longer matches the configuration that exists in AWS.

The tool compares Terraform's recorded expected state with live AWS inventory, identifies the difference, classifies its risk, recommends a safe next action, and records a tamper-evident audit trail. It never runs `terraform apply`, changes Terraform state, or calls AWS mutation APIs.

## Platform Capabilities

| Capability | What it provides |
| --- | --- |
| Expected versus live comparison | Loads Terraform state through `terraform show -json`, collects supported AWS configuration through read-only APIs, and compares normalized resource snapshots. |
| Drift taxonomy | Classifies every finding as `missing`, `unmanaged`, or `modified`, so teams can distinguish deleted resources, AWS-only resources, and changed configuration. |
| Risk classification | Uses modular severity rules to classify findings as minor, moderate, severe, or critical. Public SSH, RDP, and all-port security-group exposure are treated as critical risks; public RDS exposure and weakened RDS encryption or deletion protection are treated as severe. |
| Reports and audit history | Produces a Markdown report grouped by resource category and severity, plus hash-chained JSONL audit events for each scan, finding, and recommendation. |
| Read-only AWS access | Uses a dedicated least-privilege AWS policy and only `Describe`, `List`, and `Get` collection APIs. The scanner observes and reports; it does not apply remediation. |
| Environment scoping | Supports repeatable `--tag KEY=VALUE` filters so a scan can focus on one environment without unrelated regional resources creating findings. |
| Current AWS coverage | EC2 instances, security groups and their inline or standalone Terraform rules, S3 bucket public-access and encryption controls, VPCs, subnets, internet gateways, NAT gateways, route tables, network ACLs, IAM roles and instance profiles, Application Load Balancers, target groups, listeners, listener rules, RDS DB instances, ECS clusters, task definitions and services, Lambda functions, scheduled EventBridge rules and targets, CloudWatch log groups, EKS clusters and managed node groups, plus Route 53 hosted zones and records. Unsupported Terraform types are reported as collection diagnostics rather than misclassified as drift. |
| Extension model | Future AWS services will be added through the same adapter, collector, comparison, severity, reporting, and validation pattern. Each supported service is documented here when it becomes part of the tool. |
| Automation (planned) | Automated Jenkins and GitHub Actions workflows are planned, but are not included yet. When added, they will run scheduled and on-demand scans, retain reports and audit logs, and notify teams about critical drift. |

## How DriftCTL Is Used

DriftCTL has two ways of being used:

- **Manual Scanning:** Scenario: *(After a Terraform apply, during an investigation, or before an approved change, an engineer runs a read-only scan against the applied Terraform state and the corresponding AWS environment.)* DriftCTL reports supported differences inside the chosen tag scope. It can be used for production or non-production infrastructure when the team applies its normal access controls and change process. See the [Usage Guide](docs/USAGE.md) for the complete first-time and repeatable manual-scanning workflow.

- **Scheduled Automation:** A Jenkins pipeline or GitHub Actions workflow runs the same read-only comparison on a team-defined schedule or on demand, retains reports and audit records, and notifies the team about critical findings via Slack. *(P.S. This automation feature is not implemented yet. It is planned as an additional way for teams to use the tool.)*

The optional controlled-validation sections in the setup guide document how this project verified real detection behavior in a non-production environment. They are not a third operating mode and are not required before using DriftCTL in production. In routine use, DriftCTL reports whatever supported drift already exists; it does not expect a team to create drift first.

> [!NOTE]
> DriftCTL reads applied Terraform state with `terraform show -json`. It does not run `terraform init`, `terraform plan`, `terraform apply`, or `terraform refresh`, and it does not call AWS APIs that create, update, or delete resources.

> [!NOTE]
> Current coverage boundaries: DriftCTL supports Application Load Balancers, but not Network or Gateway Load Balancers. It does not evaluate target registration or runtime target health. RDS coverage is limited to DB instances, not Aurora clusters. When the tool cannot determine a reliable impact for a difference, it reports `NOT ASSESSED` instead of overstating risk.

## How DriftCTL Works

Terraform establishes the intended environment. DriftCTL later compares Terraform's applied state with the configuration AWS reports, without changing either one.

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
          Markdown report grouped by category and severity     Append-only JSONL audit history
                          |                                                 |
                          +------------------------+------------------------+
                                                   |
                                                   v
                              Human review and approved remediation
                        Terraform change or AWS correction; never automatic
```

Today, an engineer starts the scan manually from the command line. Planned Jenkins and GitHub Actions automation will call the same read-only scan coordinator; they do not change the comparison, risk, reporting, or remediation boundaries.

The Terraform and boto3 adapters convert provider-specific data into common `ResourceSnapshot` objects. The detector compares those normalized snapshots rather than raw Terraform state or AWS API responses. This separation keeps collection logic, comparison logic, and reporting policies independent.

## Quick Start

[![Quick DriftCTL walkthrough](https://img.shields.io/badge/Quick%20Walkthrough-CLI%20%7C%20Web%20GUI%20%7C%20AI%20Agents-2563EB?style=for-the-badge)](GOOGLE_DRIVE_VIDEO_URL)

> [!NOTE]
> `GOOGLE_DRIVE_VIDEO_URL` is a placeholder. It will be replaced with the public walkthrough link when the video is published.

DriftCTL is designed to inspect **your existing Terraform-managed AWS environment**. You clone the repository, install the command locally, configure a dedicated read-only AWS identity, and run the scan from your own Terraform project's applied state. Install Git, Python 3.11+, Terraform, and AWS CLI first; the detailed, first-time-user guide is [`docs/USAGE.md`](docs/USAGE.md).

> [!WARNING]
> Begin with a non-production environment. DriftCTL does not mutate AWS or Terraform, but its reports can contain sensitive infrastructure details.

1. Clone the repository and enter it:

```powershell
git clone https://github.com/heyohjayy/DriftCTL.git
```

```powershell
cd DriftCTL
```

2. Create and activate a Python 3.11+ environment.

**Windows PowerShell**

```powershell
py -3 -m venv .venv
```

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

```powershell
.\.venv\Scripts\Activate.ps1
```

**macOS or Linux (Bash/Zsh)**

```bash
python3 -m venv .venv
```

```bash
source .venv/bin/activate
```

In either case, first confirm the selected Python version is 3.11 or later.

3. Install DriftCTL:

```powershell
python -m pip install -e ".[dev]"
```

4. Attach the dedicated read-only policy from [`infra/iam/driftctl-read-only-policy.json`](infra/iam/driftctl-read-only-policy.json) to an AWS identity such as `driftctl-readonly`. Configure that identity through your approved AWS credential method.

5. In the root of **your own Terraform project**, verify that Terraform can read its applied state.

**Windows PowerShell**

```powershell
terraform show -json | Out-Null
```

**macOS or Linux (Bash/Zsh)**

```bash
terraform show -json > /dev/null
```

6. Copy [`examples/driftctl.toml.example`](examples/driftctl.toml.example) to `driftctl.toml` in that Terraform project. Set its AWS profile, region, optional tag scope, report path, and audit path. The full [Usage Guide](docs/USAGE.md#6-choose-your-first-scan) includes the exact configuration and platform-specific copy commands.

7. With the DriftCTL virtual environment still active, work from your Terraform project and scan:

```powershell
driftctl scan
```

DriftCTL writes a report and tamper-evident audit evidence, then exits `0` when clean, `2` when it finds drift, or `1` when the scan cannot complete. A finding is evidence for a human decision, never automatic remediation.

No Terraform infrastructure yet? Use the no-cost, disposable [live-usage sample](examples/live-usage/) or the credential-free [offline fixtures](examples/) described in the full [Usage Guide](docs/USAGE.md).

## Learn More

- [Usage guide](docs/USAGE.md): the complete first-time-user workflow for scanning your own Terraform-managed AWS environment.
- [Controlled validation lab](docs/VALIDATION.md): the project's own non-production test infrastructure, deliberate drift scenarios, evidence screenshots, remediation, and cleanup record.
- [Terraform infrastructure](infra/terraform/README.md): the version-controlled non-production infrastructure reference used for this project's controlled live validation.
- [Read-only IAM policy](infra/iam/driftctl-read-only-policy.json): the least-privilege AWS inspection policy used by the live-scan workflow. The usage guide explains how to apply it safely.
- [License](LICENSE): GNU Affero General Public License v3.0 permissions, conditions, and limitations. Modified versions offered to users over a network must provide their corresponding source code under the same license.
- [Evidence index](docs/screenshots/README.md): screenshots from the offline and controlled live-validation demonstrations.
