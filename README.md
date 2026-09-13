# Infrastructure Drift Control Platform

`driftctl` is a read-only Terraform drift-detection and remediation-planning tool for AWS. It helps teams identify and safely resolve Terraform state drift: the common situation where a Terraform-managed environment no longer matches the configuration that exists in AWS.

The tool compares Terraform's recorded expected state with live AWS inventory, identifies the difference, classifies its risk, recommends a safe next action, and records an append-only audit trail. It never runs `terraform apply`, changes Terraform state, or calls AWS mutation APIs.

## Platform Capabilities

| Capability | What it provides |
| --- | --- |
| Expected versus live comparison | Loads Terraform state through `terraform show -json`, collects supported AWS configuration through read-only APIs, and compares normalized resource snapshots. |
| Drift taxonomy | Classifies every finding as `missing`, `unmanaged`, or `modified`, so teams can distinguish deleted resources, AWS-only resources, and changed configuration. |
| Risk classification | Uses modular severity rules to classify findings as minor, moderate, severe, or critical. Public SSH, RDP, and all-port security-group exposure are treated as critical risks. |
| Reports and audit history | Produces a Markdown report grouped by resource category and severity, plus append-only JSONL audit events for each scan, finding, and recommendation. |
| Read-only AWS access | Uses a dedicated least-privilege AWS policy and only `Describe`, `List`, and `Get` collection APIs. The scanner observes and reports; it does not apply remediation. |
| Environment scoping | Supports repeatable `--tag KEY=VALUE` filters so a scan can focus on one environment without unrelated regional resources creating findings. |
| Current AWS coverage | EC2 instances, security groups and their inline or standalone Terraform rules, S3 bucket public-access and encryption controls, VPCs, subnets, internet gateways, route tables, network ACLs, IAM roles and instance profiles, plus Route 53 hosted zones and records. Unsupported Terraform types are reported as collection diagnostics rather than misclassified as drift. |
| Extension model | Each additional AWS service follows the same adapter, collector, comparison, severity, reporting, and validation pattern. This keeps later coverage additions consistent with the existing read-only drift workflow. |
| Team operation | The intended operational model supports direct CLI use and a dedicated Jenkins monitoring pipeline for scheduled and manual scans, report and audit retention, and critical-drift notifications. GitHub Actions can also serve as an additional runner. |

## Quick Start

The offline demonstration is the fastest way to see the tool work. It uses included fixture files that resemble Terraform state and boto3 responses, so it does not access an AWS account or require credentials.

Python 3.11 or later is required. From the repository directory, create and activate an isolated Python environment:

```powershell
python -m venv .venv
```

```powershell
.venv\Scripts\Activate.ps1
```

Install the project and development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Run the offline scan:

```powershell
driftctl scan --expected examples\expected.json --live examples\live.json --report reports\offline-drift-report.md --audit audit\offline-events.jsonl
```

The command writes a Markdown report and appends JSONL audit events. This credential-free workflow is useful for local evaluation, development, and CI.

For a complete step-by-step guide to using DriftCTL manually, including safe live AWS testing and evidence screenshots, read [the setup and usage guide](docs/SETUP.md).

## Safe Live AWS Scan

Use an initialized Terraform working directory with access to the state you intend to inspect. DriftCTL runs only `terraform show -json`; it does not run `init`, `plan`, `apply`, or `refresh`.

Attach [the supplied read-only IAM policy](infra/iam/driftctl-read-only-policy.json) to the collecting principal or assumed role. When using `--role-arn`, the source principal also needs a narrowly scoped `sts:AssumeRole` permission for that role. Copy [the sample environment file](examples/aws-demo.env.example) as a reference for configuration values, but do not store AWS credentials in it.

The following command scans one tagged environment. Replace the Terraform directory, region, and tag with values for your own non-production infrastructure:

```powershell
driftctl scan `
  --terraform-dir C:\path\to\your\terraform-project `
  --profile driftctl-readonly `
  --region eu-west-1 `
  --tag Project=Test `
  --report reports\live-baseline-report.md `
  --audit audit\live-baseline-events.jsonl
```

### Reuse a Scan Configuration

The full command is useful because it shows every setting DriftCTL needs. If you scan the same Terraform environment regularly, you can save those settings in one small local file named `driftctl.toml`. This saves you from typing the same long command every time.

Put `driftctl.toml` in the top folder of the Terraform project it describes. The file stores the Terraform folder, AWS CLI profile name, AWS region, tag scope, and report and audit locations. It does not store credentials. Start from [the configuration example](examples/driftctl.toml.example).

After activating the Python environment, move into the Terraform project. When `driftctl.toml` is in that folder, run:

```powershell
driftctl scan
```

You can also run the same scan from any directory by giving the configuration file path:

```powershell
driftctl scan --config C:\path\to\your\terraform-project\driftctl.toml
```

Paths inside `driftctl.toml` are based on the location of the configuration file, not the folder currently open in the terminal. You can still add command options when needed. For example, `--report` replaces the report path saved in the file for one scan. Never put AWS access keys, secret access keys, session tokens, passwords, or other credentials in this file.

`--expected` and `--terraform-dir` are mutually exclusive. Supplying `--live` keeps the scan offline; omitting it enables AWS collection and requires an explicit `--region`.

Use repeatable `--tag KEY=VALUE` options to restrict a scan to resources that match every supplied tag. The scope is applied to both expected and live snapshots, so resources outside it cannot create missing, unmanaged, or modified findings. The report and audit log record the active scope for later review.

See [the architecture notes](docs/architecture.md) for the processing flow and [the setup guide](docs/SETUP.md) for the full manual workflow.
