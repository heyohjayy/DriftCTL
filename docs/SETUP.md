# Setup and Usage Guide

This guide is for anyone who has found the project repository and wants to run it themselves. It starts with a completely safe offline demonstration, then explains how to connect the scanner to a non-production AWS environment.

Infrastructure Drift Control is read-only. It compares Terraform's recorded state with AWS's current configuration, writes a report, and recommends remediation. It does not run `terraform apply`, change Terraform state, or modify AWS resources.

## What You Will Do

1. Download the project and install its Python dependencies.
2. Run the automated tests.
3. Run an offline drift scan using included example data.
4. Optionally scan your own Terraform-managed AWS environment with read-only credentials.
5. Optionally introduce harmless test drift and confirm the report detects it.

## Prerequisites

Install the following before beginning.

- **Git**: downloads the project and records your own changes.
- **Python 3.11 or later**: runs the command-line tool.
- **Terraform**: required only when scanning real Terraform state.
- **AWS CLI**: required only when scanning a real AWS environment.
- **An AWS account or sandbox environment**: required only for the live AWS demonstration. Do not begin with production infrastructure.

Check the locally installed versions in PowerShell:

```powershell
git --version
python --version
terraform --version
aws --version
```

`terraform` and `aws` may be unavailable at this point. That is fine if you are completing only the offline demonstration.

## 1. Clone the Repository

Open PowerShell in a folder where you keep development projects, then clone your fork or the original repository:

```powershell
git clone <repository-url>
cd infra-drift-control
```

Replace `<repository-url>` with the HTTPS or SSH URL shown by GitHub's **Code** button.

Screenshot placeholder: `01-clone-repository.png` should show the GitHub repository page with the Code button or the successful `git clone` command. Do not include browser tabs containing credentials.

## 2. Create an Isolated Python Environment

A virtual environment keeps this project's Python packages separate from packages used by other projects on your computer.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The `-e` flag installs the project in editable mode. Changes you make in `src/` are immediately used the next time you run `driftctl`; you do not need to reinstall after every code change.

If PowerShell blocks the activation script, run this one-time command for the current terminal session and then repeat the activation command:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Screenshot placeholder: `02-python-environment.png` should show the activated `.venv` prompt and successful dependency installation.

## 3. Run the Test Suite

Run the tests before using the scanner. The tests use stubbed AWS responses and do not access your AWS account.

```powershell
pytest
```

Expected result: all tests pass. A failure should be investigated before relying on the scanner for a live environment.

Screenshot placeholder: `03-tests-passing.png` should show the final passing-test summary only. Avoid including unrelated terminal output.

## 4. Run the Safe Offline Demonstration

The project includes two fixture files:

- `examples/expected.json`: Terraform-state-shaped expected infrastructure.
- `examples/live.json`: boto3-response-shaped current AWS infrastructure.

Run the scanner against them:

```powershell
driftctl scan `
  --expected examples/expected.json `
  --live examples/live.json `
  --report reports/drift-report.md `
  --audit audit/events.jsonl
```

The command creates two local outputs:

- `reports/drift-report.md`: a Markdown report grouped by resource category and severity.
- `audit/events.jsonl`: an append-only event log, with one JSON object per line.

These generated files are intentionally excluded from Git. They can contain real infrastructure metadata when you perform a live scan.

Open the report in your editor and read the findings. Each finding is one of three drift types:

- `missing`: Terraform expects a resource that AWS no longer has.
- `unmanaged`: AWS has a resource not represented in Terraform's expected inventory.
- `modified`: both sources identify the resource, but one or more properties differ.

Screenshot placeholder: `04-offline-drift-report.png` should show a sanitized report with its category and severity headings visible.

## 5. Prepare a Safe Live AWS Demonstration

Complete this section only after the offline command and tests work.

Use a dedicated AWS sandbox account whenever possible. If you only have one personal AWS account, use a clearly labelled development environment with small, disposable resources. Never start with production infrastructure.

### Create Test Infrastructure

Create a small Terraform project that manages at least an EC2 instance and a security group. Apply it once:

```powershell
terraform init
terraform plan
terraform apply
```

Terraform state records the last configuration Terraform applied. The scanner compares that record against the configuration AWS returns now.

Keep the Terraform project separate from this repository. It is a temporary demonstration environment, while Infrastructure Drift Control is the reusable product.

### Configure Read-Only AWS Access

Use the least-privilege policy at `infra/iam/driftctl-read-only-policy.json` to create a dedicated read-only IAM principal or role. Configure its credentials locally as an AWS CLI profile:

```powershell
aws configure --profile driftctl-readonly
aws sts get-caller-identity --profile driftctl-readonly
```

The first command writes credentials to your local AWS configuration. Never add these credentials to this repository, an `.env` file, a screenshot, or a chat message. The second command confirms which AWS identity the profile uses.

### Run the Live Scan

From the Infrastructure Drift Control repository, replace the Terraform path and region below with your own values:

```powershell
driftctl scan `
  --terraform-dir C:\path\to\your\terraform-project `
  --profile driftctl-readonly `
  --region eu-west-1 `
  --report reports\aws-drift-report.md `
  --audit audit\events.jsonl
```

The first live run is the **baseline scan**. Immediately after a successful Terraform apply, it should show no unexpected drift. If it reports a collection diagnostic, read the message before continuing; do not treat a failed collection as a clean scan.

Screenshot placeholder: `05-live-baseline-scan.png` should show the command result and a sanitized clean summary. Hide account IDs, IP addresses, and resource IDs.

## 6. Demonstrate Drift Deliberately

After recording a clean baseline, create safe drift manually in the AWS Console.

1. Add a non-sensitive tag, such as `Owner=Demo`, to the test EC2 instance.
2. Run the live scan again.
3. Confirm the finding is `modified` with `minor` severity.
4. Remove the tag using Terraform and run the scanner once more to confirm the environment is clean.

For a critical security demonstration, use an unattached, dedicated test security group. Add a world-accessible SSH rule only long enough to run the scan, then remove it immediately. Never run this demonstration against production infrastructure or an instance you depend on.

Screenshot placeholder: `06-minor-tag-drift.png` should show the minor tag finding.

Screenshot placeholder: `07-critical-security-drift.png` should show a sanitized critical finding without account IDs, public IPs, or resource IDs.

## 7. Clean Up the Demo Environment

When you finish testing, switch to the separate Terraform demonstration project and remove its resources:

```powershell
terraform destroy
```

Read the destroy plan carefully before confirming. This command deletes the resources Terraform created in that state, and prevents unnecessary ongoing AWS charges.

## Troubleshooting

### `driftctl` Is Not Recognized

Activate the virtual environment again:

```powershell
.venv\Scripts\Activate.ps1
```

Then reinstall the project:

```powershell
python -m pip install -e ".[dev]"
```

### AWS Credentials Cannot Be Found

Check that the expected profile exists and that you passed the same profile name to `--profile`:

```powershell
aws sts get-caller-identity --profile driftctl-readonly
```

### Terraform State Cannot Be Read

Run the live scan against the Terraform working directory that owns the applied state. Confirm this command succeeds in that directory:

```powershell
terraform show -json
```

Do not commit the output because it may contain account-specific resource data.
