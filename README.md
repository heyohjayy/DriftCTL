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
  <a href="NOTICE"><img src="https://img.shields.io/badge/Copyright-2026%20heyohjayy-5E2CA5" alt="DriftCTL copyright notice"></a>
  <a href="CONTRIBUTING.md"><img src="https://img.shields.io/badge/Contributions-Welcome-2EA44F" alt="Contributions welcome"></a>
</p>

<p align="center"><strong>Detect Terraform-to-AWS drift before it becomes operational debt.</strong></p>

`DriftCTL` is a read-only Terraform drift-detection and remediation-planning tool for AWS. It helps teams identify and safely resolve Terraform state drift: the common situation where a Terraform-managed environment no longer matches the configuration that exists in AWS.

The tool compares Terraform's recorded expected state with live AWS inventory, identifies the difference, classifies its risk, recommends a safe next action, and records a hash-chained audit trail. It never runs `terraform apply`, changes Terraform state, or calls AWS mutation APIs.

## Core Features

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
| Automation | Jenkins and GitHub Actions workflows run scheduled and on-demand scans, retain reports and audit logs, and notify teams about critical drift without changing DriftCTL's read-only decision boundary. |

## How DriftCTL Is Used

DriftCTL supports two team workflows:

- **Manual scanning:** After a Terraform apply, during an investigation, or before an approved change, an engineer runs a read-only scan against the applied Terraform state and corresponding AWS environment. DriftCTL reports supported differences within the chosen tag scope. It can inspect production or non-production infrastructure when the team applies its normal access controls and change process. See the [Usage Guide](docs/USAGE.md) for the complete first-time and repeatable manual workflow.

- **Scheduled automation:** A Jenkins pipeline or GitHub Actions workflow runs the same read-only comparison on a team-defined schedule or on demand, retains reports and audit records, and notifies the team about critical findings through the team's chosen notification channel.

The optional controlled-validation procedures in [the validation guide](docs/VALIDATION.md) document how DriftCTL's detection behavior was verified in a non-production environment. They are evidence, not a third operating mode or a prerequisite for using DriftCTL. In routine use, DriftCTL reports supported drift that already exists; teams do not need to create drift first.

> [!NOTE]
> DriftCTL reads applied Terraform state with `terraform show -json`. It does not run `terraform init`, `terraform plan`, `terraform apply`, or `terraform refresh`, and it does not call AWS APIs that create, update, or delete resources.

> [!NOTE]
> Current coverage boundaries: DriftCTL supports Application Load Balancers, but not Network or Gateway Load Balancers. It does not evaluate target registration or runtime target health. RDS coverage is limited to DB instances, not Aurora clusters. When the tool cannot determine a reliable impact for a difference, it reports `NOT ASSESSED` instead of overstating risk.

## Quick Walkthrough Video

[![Watch the DriftCTL quick walkthrough video](https://drive.google.com/thumbnail?id=1bxpyVSQ1-5rGvXKs6S5Fe4Eo3kD3c4rV&sz=w1200)](https://drive.google.com/file/d/1bxpyVSQ1-5rGvXKs6S5Fe4Eo3kD3c4rV/view?usp=sharing)

## Quick Start

DriftCTL is designed to inspect **your existing Terraform-managed AWS environment**. Install the released package, configure a dedicated read-only AWS identity, and run the scan from your own Terraform project's applied state. You need Python 3.11+, `pipx`, Terraform, and AWS CLI; the detailed, first-time-user guide is [`docs/USAGE.md`](docs/USAGE.md).

> [!WARNING]
> Begin with a non-production environment. DriftCTL does not mutate AWS or Terraform, but its reports can contain sensitive infrastructure details.

1. Install `pipx`. It installs the DriftCTL command in an isolated environment without requiring a repository clone. Platform-specific commands are in the [Usage Guide](docs/USAGE.md#3-install-required-tools).

<details>
<summary><strong>Linux: install pipx</strong></summary>

Run this as one pasted Bash command. The trailing backslashes continue the command onto the next line; they are not separate commands.

```bash
sudo apt update && \
sudo apt install -y python3-pip pipx && \
pipx ensurepath && \
export PATH="$HOME/.local/bin:$PATH"
```

This path is for Ubuntu or Debian. `pipx ensurepath` makes the command available in future terminals; the final `export` also makes it available in the terminal you are using now.

</details>

2. Install the released package and confirm the product command:

```bash
pipx install drift-control
```

```bash
driftctl --help
```

3. Attach the dedicated read-only policy from [`infra/iam/driftctl-read-only-policy.json`](infra/iam/driftctl-read-only-policy.json) to an AWS identity such as `driftctl-readonly`, then configure that identity for your terminal.

<details>
<summary><strong>How to create the read-only policy and connect your terminal</strong></summary>

1. In the AWS Console, open **IAM** and choose **Policies**.
2. Choose **Create policy**, then choose the **JSON** editor.
3. Open [`infra/iam/driftctl-read-only-policy.json`](infra/iam/driftctl-read-only-policy.json), copy its complete contents, replace the editor contents, then choose **Next**.
4. Name the policy, for example `DriftCTLReadOnly`, and create it.
5. Attach it to a dedicated IAM user, IAM role, or IAM Identity Center permission set. Do not attach it to the identity that applies Terraform unless your organisation explicitly requires that arrangement.
6. Choose the AWS credential method your environment already uses:
   - **IAM Identity Center (SSO):** use this only if your organization provides an AWS access portal URL and SSO Region.
   - **Dedicated shared AWS CLI profile:** use this in a personal or learning account that permits programmatic IAM-user credentials.
   - **Existing approved profile or assumed role:** use it directly; do not reconfigure it.

<details>
<summary><strong>Option A: IAM Identity Center (SSO)</strong></summary>

Use this only when your organization provides IAM Identity Center access. An administrator can find the portal URL in AWS Console under **IAM Identity Center** > **Settings** > **AWS access portal URL**. It usually looks like `https://d-xxxxxxxxxx.awsapps.com/start`; it is not the normal AWS Console URL. Then run:

```powershell
aws configure sso --profile driftctl-readonly
```

At the interactive prompts, use a local session name such as `driftctl-sso`, paste the access portal URL, select the SSO Region supplied by your organization, accept the default `sso:account:access` registration scope unless instructed otherwise, then select the account and read-only role your administrator assigned. Choose the AWS Region that contains the infrastructure you plan to scan as the profile's default Region.

```powershell
aws sso login --profile driftctl-readonly
```

</details>

<details>
<summary><strong>Option B: Dedicated shared AWS CLI profile</strong></summary>

Use this in a personal or learning account only when programmatic IAM-user credentials are permitted. Run the following and enter only credentials for the read-only identity. Treat the access key and secret key as private credentials: never share them, and make sure they are not visible in recordings or screenshots.

Before running it, obtain those values from **AWS Console** > **IAM** > **Users** > select the dedicated read-only user > **Security credentials** > **Access keys** > **Create access key**. Select **Command Line Interface (CLI)**, then copy the access key ID and secret access key when AWS displays them. The secret key is shown only once.

```powershell
aws configure --profile driftctl-readonly
```

At the prompts, enter the new read-only user's access key ID and secret access key, choose the AWS Region containing the infrastructure you will scan, and enter `json` for output. The [Usage Guide](docs/USAGE.md#5-prepare-aws-read-only-access) explains each prompt in detail.

</details>

<details>
<summary><strong>Option C: Existing approved profile or assumed role</strong></summary>

Use the existing profile or role name directly. Do not run either configuration command above.

</details>

7. Verify the chosen profile:

```powershell
aws sts get-caller-identity --profile driftctl-readonly
```

`driftctl-readonly` is an example profile name. Replace it with your own read-only AWS profile name throughout this Quick Start.

> **Warning:** Do not use administrator credentials for scanning. The DriftCTL identity needs only the read-only policy supplied by this repository.

</details>

4. In the root of **your own Terraform project**, verify that Terraform can read its applied state.

**Windows PowerShell**

```powershell
terraform show -json | Out-Null
```

**macOS or Linux (Bash/Zsh)**

```bash
terraform show -json > /dev/null
```

5. Create the scan configuration in that Terraform project:

```bash
driftctl init
```

Enter the read-only AWS CLI profile, AWS Region, and optional `KEY=VALUE` tag scope when prompted. The command writes a non-secret `driftctl.toml`; it never stores AWS credentials.

6. Scan from that Terraform project:

```powershell
driftctl scan
```

DriftCTL writes a report and hash-chained audit evidence, then exits `0` when clean, `2` when it finds drift, or `1` when the scan cannot complete. A finding is evidence for a human decision, never automatic remediation.

No Terraform infrastructure yet? Use the no-cost, disposable [live-usage sample](examples/live-usage/) or the credential-free [offline fixtures](examples/) described in the full [Usage Guide](docs/USAGE.md). For a direct Ubuntu/Debian walkthrough that uses the disposable example, see the [Linux quick walkthrough](docs/LINUX_USAGE.md). Contributors and users who want repository examples can still [install from source](docs/USAGE.md#install-from-source-optional).

## Learn More

- [Usage guide](docs/USAGE.md): the complete first-time-user workflow for scanning your own Terraform-managed AWS environment.
- [Linux quick walkthrough](docs/LINUX_USAGE.md): one copy-ready Ubuntu/Debian path using separate Terraform-admin and read-only scanning profiles with the disposable example.
- [Architecture](docs/ARCHITECTURE.md): the scan pipeline, provider-neutral data model, safety boundaries, evidence design, and extension model.
- [Controlled validation lab](docs/VALIDATION.md): the project's own non-production test infrastructure, deliberate drift scenarios, evidence screenshots, remediation, and cleanup record.
- [Terraform infrastructure](infra/terraform/README.md): the version-controlled non-production infrastructure reference used for this project's controlled live validation.
- [Read-only IAM policy](infra/iam/driftctl-read-only-policy.json): the least-privilege AWS inspection policy used by the live-scan workflow. The usage guide explains how to apply it safely.
- [Changelog](CHANGELOG.md): release history and the current release's known boundaries.
- [Publishing guide](docs/PUBLISHING.md): maintainer-only PyPI trusted-publishing and release procedure.
- [License](LICENSE): GNU Affero General Public License v3.0 permissions, conditions, and limitations. Modified versions offered to users over a network must provide their corresponding source code under the same license.
- [Copyright notice](NOTICE): ownership, license reference, redistribution, third-party-material, and warranty notices for DriftCTL.
- [Evidence index](docs/screenshots/README.md): screenshots from the offline and controlled live-validation demonstrations.
