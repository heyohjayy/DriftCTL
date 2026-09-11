# Setup and Usage Guide

This guide is for anyone who has found the project repository and wants to run it themselves. It starts with a completely safe offline demonstration, then explains how to connect the scanner to a non-production AWS environment.

Infrastructure Drift Control is read-only. It compares Terraform's recorded state with AWS's current configuration, writes a report, and recommends remediation. It does not run `terraform apply`, change Terraform state, or modify AWS resources.

## What You Will Do

1. Download the project and install its Python dependencies.
2. Run the automated tests.
3. Run an offline drift scan using included example data.
4. Optionally scan your own Terraform-managed AWS environment with read-only credentials.
5. Optionally run controlled live drift-validation tests and return the environment to a clean state.

## Prerequisites

Install the following before beginning.

- **Git**: downloads the project and records your own changes.
- **Python 3.11 or later**: runs the command-line tool.
- **Terraform**: required only when scanning real Terraform state.
- **AWS CLI**: required only when scanning a real AWS environment.
- **An AWS account or sandbox environment**: required only for the live AWS demonstration. Do not begin with production infrastructure.

Check that Git is available:

```powershell
git --version
```

Check that Python is available:

```powershell
python --version
```

Check that Terraform is available for a future live scan:

```powershell
terraform --version
```

Check that the AWS CLI is available for a future live scan:

```powershell
aws --version
```

`terraform` and `aws` may be unavailable at this point. That is fine if you are completing only the offline demonstration.

## 1. Clone the Repository

Open PowerShell in a folder where you keep development projects. Download your fork or the original repository:

```powershell
git clone <repository-url>
```

Move into the newly downloaded project directory:

```powershell
cd infra-drift-control
```

Replace `<repository-url>` with the HTTPS or SSH URL shown by GitHub's **Code** button.

## 2. Create an Isolated Python Environment

A virtual environment keeps this project's Python packages separate from packages used by other projects on your computer.

Run these commands one at a time from the cloned project directory.

Confirm the Python version that will create the virtual environment:

```powershell
python --version
```

Create a local virtual environment named `.venv`:

```powershell
python -m venv .venv
```

Allow the activation script in this PowerShell window only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Activate the virtual environment. The prompt should begin with `(.venv)` afterward:

```powershell
.\.venv\Scripts\Activate.ps1
```

Update `pip`, Python's package installer:

```powershell
python -m pip install --upgrade pip
```

Install DriftCTL and its development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

The `-e` flag installs the project in editable mode. Changes you make in `src/` are immediately used the next time you run `driftctl`; you do not need to reinstall after every code change.

The execution-policy command applies only to the current PowerShell window. It allows the local virtual-environment activation script to run; it does not permanently change the computer's policy.

![Local Python environment setup, part one](screenshots/01a-local-environment-setup.png)

![Local Python environment setup, part two](screenshots/01b-local-environment-setup.png)

## 3. Run the Test Suite

Run the tests before using the scanner. The tests use stubbed AWS responses and do not access your AWS account. The `-q` option keeps the output compact for easier reading.

```powershell
pytest -q
```

Expected result: all tests pass. A failure should be investigated before relying on the scanner for a live environment.

![Passing automated tests](screenshots/02-tests-passing.png)

## 4. Run the Safe Offline Demonstration

The project includes two fixture files:

- `examples/expected.json`: Terraform-state-shaped expected infrastructure.
- `examples/live.json`: boto3-response-shaped current AWS infrastructure.

Run the scanner against those local fixture files. This command does not contact AWS:

```powershell
driftctl scan --expected examples\expected.json --live examples\live.json --report reports\offline-drift-report.md --audit audit\offline-events.jsonl
```

The command creates two local outputs:

- `reports/offline-drift-report.md`: a Markdown report grouped by resource category and severity.
- `audit/offline-events.jsonl`: an append-only event log, with one JSON object per line.

These generated files are intentionally excluded from Git. They can contain real infrastructure metadata when you perform a live scan.

Display the generated Markdown report in PowerShell:

```powershell
Get-Content .\reports\offline-drift-report.md
```

Each finding is one of three drift types:

- `missing`: Terraform expects a resource that AWS no longer has.
- `unmanaged`: AWS has a resource not represented in Terraform's expected inventory.
- `modified`: both sources identify the resource, but one or more properties differ.

![Offline drift scan and report](screenshots/03-offline-drift-report.png)

## 5. Prepare a Safe Live AWS Demonstration

Complete this section only after the offline command and tests work.

Use a dedicated AWS sandbox account whenever possible. If you only have one personal AWS account, use a clearly labelled development environment with small, disposable resources. Never start with production infrastructure.

### Create Test Infrastructure

Before continuing, have a separate non-production Terraform project that manages at least one EC2 instance and one security group. Give every resource that you want to scan the same environment tag, such as `Project = "Test"`. Keep this Terraform project outside the DriftCTL repository, because it is a temporary demo environment rather than part of the product.

Initialize the Terraform working directory:

```powershell
terraform init
```

Preview Terraform's intended changes and review them carefully:

```powershell
terraform plan
```

Apply only after you have reviewed the plan:

```powershell
terraform apply
```

Terraform state records the last configuration Terraform applied. The scanner compares that record against the configuration AWS returns now.

Keep the Terraform project separate from this repository. It is a temporary demonstration environment, while Infrastructure Drift Control is the reusable product.

### Configure Read-Only AWS Access

Use the least-privilege policy at `infra/iam/driftctl-read-only-policy.json` to create a dedicated read-only IAM principal or role. Configure its credentials locally as an AWS CLI profile. Enter credentials only into the private terminal prompts:

```powershell
aws configure --profile driftctl-readonly
```

Confirm that the configured profile can authenticate:

```powershell
aws sts get-caller-identity --profile driftctl-readonly
```

The first command writes credentials to your local AWS configuration. Never add these credentials to this repository, an `.env` file, a screenshot, or a chat message. The second command confirms which AWS identity the profile uses. If you document this step, cover the entire access-key and secret-key values with opaque blocks before saving the screenshot.

![Read-only AWS profile configuration and verification](screenshots/04a-read-only-profile-verification.png)

### Run the Live Scan

From the Infrastructure Drift Control repository, replace the Terraform path and region below with your own values:

```powershell
driftctl scan --terraform-dir C:\path\to\your\terraform-project --profile driftctl-readonly --region eu-west-1 --tag Project=Test --report reports\aws-drift-report.md --audit audit\events.jsonl
```

The first live run is the **baseline scan**. Immediately after a successful Terraform apply, it should show no unexpected drift. If it reports a collection diagnostic, read the message before continuing; do not treat a failed collection as a clean scan.

### Scope a Live Scan by Environment Tag

Use repeatable `--tag KEY=VALUE` options to scan only one environment. All supplied tags must match. The scanner filters both Terraform and AWS inventories, preventing unrelated regional resources from producing findings. EC2 instances and security groups are filtered by their AWS `Describe` calls; S3 buckets are filtered after their read-only tags are collected. The report includes an **Active tag scope** collection diagnostic so the scan boundary is visible later.

Every resource you want in the scoped scan must carry the tag. For example, add `Project = "Test"` to the Terraform `tags` block for both the EC2 instance and its security group, then review and apply Terraform's plan.

Run a scoped baseline with your own Terraform directory. Replace `C:\path\to\your\terraform-project` with the directory that owns your applied Terraform state:

```powershell
driftctl scan --terraform-dir C:\path\to\your\terraform-project --profile driftctl-readonly --region eu-west-1 --tag Project=Test --report reports\live-baseline-report.md --audit audit\live-baseline-events.jsonl
```

Then display the report to confirm the collection diagnostics, scope, resource counts, and finding count:

```powershell
Get-Content .\reports\live-baseline-report.md
```

A successful baseline reports matching expected and live counts, `0` findings, and `No drift detected`.

![Clean scoped live baseline](screenshots/04b-live-baseline-scan.png)

## 6. Run Controlled Live Drift Validation

This optional section proves that DriftCTL detects real differences between Terraform's expected state and AWS's live state. It deliberately makes small, temporary changes in a non-production environment, scans them, and restores the intended configuration afterward.

Only perform these tests in a sandbox. The DriftCTL command remains read-only throughout; the AWS Console changes below are made manually to create test conditions.

Use the same Terraform directory, AWS profile, region, and tag scope from the baseline scan. The examples below use `Project=Test`. Replace the Terraform path with your own path.

### Test 1: Detect Minor Tag Drift

This test proves that a metadata-only change to a Terraform-managed EC2 instance is classified as `modified` with `minor` severity.

In the AWS Console, open **EC2** then **Instances**. Select a Terraform-managed test instance that has the scope tag, such as `Project=Test`. In its **Tags** tab, add the temporary tag `Owner=Demo`. Do not remove the scope tag.

Run this scan to write a dedicated report for the test:

```powershell
driftctl scan --terraform-dir C:\path\to\your\terraform-project --profile driftctl-readonly --region eu-west-1 --tag Project=Test --report reports\minor-tag-drift-report.md --audit audit\minor-tag-drift-events.jsonl
```

Display the result so you can inspect the finding:

```powershell
Get-Content .\reports\minor-tag-drift-report.md
```

The report should show a `Compute` finding with `modified` taxonomy and `minor` severity. Remove the temporary `Owner=Demo` tag in the AWS Console before continuing.

![Minor EC2 tag drift](screenshots/05-minor-tag-drift.png)

### Test 2: Detect an Unmanaged Resource

This test proves that the selected tag scope still detects resources created in AWS but absent from Terraform.

In the AWS Console, create an **unattached security group** in the same VPC as your test infrastructure. Give it a descriptive temporary name, do not add inbound rules, and add the same scope tag, for example `Project=Test`. An unattached security group with no inbound rules does not expose an instance and does not create an EC2 running cost.

Run a dedicated scan:

```powershell
driftctl scan --terraform-dir C:\path\to\your\terraform-project --profile driftctl-readonly --region eu-west-1 --tag Project=Test --report reports\unmanaged-resource-report.md --audit audit\unmanaged-resource-events.jsonl
```

Display the report:

```powershell
Get-Content .\reports\unmanaged-resource-report.md
```

The report should show a `Networking` finding with `unmanaged` taxonomy. Delete the temporary security group in the AWS Console before continuing.

![Unmanaged in-scope security group](screenshots/06-unmanaged-resource.png)

### Test 3: Detect Critical Public SSH Drift

This test proves that a dangerous network change is classified as `modified` with `critical` severity without exposing a running workload.

Before this test, create and apply a separate **Terraform-managed, unattached** security group with the scan scope tag and no inbound rules. It must appear in Terraform state before you edit it manually. Do not use a security group attached to an EC2 instance. Confirm a scoped baseline scan returns `0` findings before proceeding.

In the AWS Console, open the detached test security group's **Inbound rules**. Add a temporary rule with type `SSH`, port `22`, and source `Anywhere-IPv4` (`0.0.0.0/0`). Save the rule, run the scan immediately, and remove the rule immediately after capturing the result.

Run the critical-drift scan:

```powershell
driftctl scan --terraform-dir C:\path\to\your\terraform-project --profile driftctl-readonly --region eu-west-1 --tag Project=Test --report reports\critical-security-drift-report.md --audit audit\critical-security-drift-events.jsonl
```

Display the report:

```powershell
Get-Content .\reports\critical-security-drift-report.md
```

The report should show a `Networking` finding with `modified` taxonomy and `critical` severity. Its rule should identify public SSH exposure. Remove the temporary SSH rule in the AWS Console immediately after reviewing the report.

![Critical public SSH drift](screenshots/07-critical-security-drift.png)

### Test 4: Confirm Remediation

After removing every temporary manual change, repeat the scoped baseline scan. This proves that the live environment again matches Terraform's expected state.

```powershell
driftctl scan --terraform-dir C:\path\to\your\terraform-project --profile driftctl-readonly --region eu-west-1 --tag Project=Test --report reports\clean-after-remediation-report.md --audit audit\clean-after-remediation-events.jsonl
```

Display the final report:

```powershell
Get-Content .\reports\clean-after-remediation-report.md
```

A successful remediation result shows matching expected and live counts, `0` findings, and `No drift detected`. You may retain the detached Terraform-managed test security group as a reusable fixture, provided it stays unattached and has no inbound rules.

![Clean scan after remediation](screenshots/08-clean-after-remediation.png)

## Troubleshooting

| Issue | Solution |
| --- | --- |
| `driftctl` is not recognized | Activate the virtual environment with `.venv\Scripts\Activate.ps1`, then reinstall the project with `python -m pip install -e ".[dev]"`. |
| AWS credentials cannot be found | Confirm the expected profile exists and use the same name with `--profile`: `aws sts get-caller-identity --profile driftctl-readonly`. |
| Terraform state cannot be read | Run the live scan against the Terraform working directory that owns the applied state. In that directory, confirm `terraform show -json` succeeds. Do not commit its output because it may contain account-specific resource data. |
