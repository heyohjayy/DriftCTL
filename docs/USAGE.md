# DriftCTL Usage Guide

This guide is for a first-time user who wants to run DriftCTL against their own Terraform-managed AWS environment. It starts with installing the required tools, connects a local terminal to AWS through a read-only identity, and ends with a repeatable scan.

> [!TIP]
> Using Ubuntu or another Debian-based Linux machine and want one direct, recordable path with the disposable example? Start with the [Linux quick walkthrough](LINUX_USAGE.md). This guide remains the cross-platform reference for all supported first-scan paths.

DriftCTL compares **applied Terraform state** with the corresponding live AWS configuration. It writes a Markdown report and a tamper-evident JSONL audit log. It never runs `terraform apply`, modifies Terraform state, or calls AWS mutation APIs.

> [!WARNING]
> Start with a non-production environment. A scan is read-only, but its report can reveal infrastructure names, IDs, networking details, and security configuration. Treat reports and audit logs as sensitive operational evidence.

> [!NOTE]
> [`docs/VALIDATION.md`](VALIDATION.md) is different from this guide. It records DriftCTL's own controlled validation labs and screenshots. You do not need to reproduce those labs to use DriftCTL on your infrastructure.

## Contents

1. [What You Need](#1-what-you-need)
2. [Command Reference](#2-command-reference)
3. [Install Required Tools](#3-install-required-tools)
4. [Install DriftCTL](#4-install-driftctl)
5. [Prepare AWS Read-Only Access](#5-prepare-aws-read-only-access)
6. [Choose Your First Scan](#6-choose-your-first-scan)
7. [Read the Results](#7-read-the-results)
8. [Run Future Scans](#8-run-future-scans)
9. [Troubleshooting](#9-troubleshooting)

## 1. What You Need

| Requirement | Why it is needed | Offline demo | Your live scan |
| --- | --- | --- | --- |
| `pipx` | Installs the DriftCTL command in an isolated environment. | Yes | Yes |
| Git | Required only for source installation or repository examples. | Optional | Optional |
| Python 3.11 or later | Runs DriftCTL. | Yes | Yes |
| Terraform CLI | Reads applied state with `terraform show -json`. | No | Yes |
| AWS CLI | Configures and verifies the AWS scanning identity. | No | Yes |
| An AWS credential method | Lets the AWS CLI use a dedicated read-only identity. | No | Yes |
| A Terraform directory with applied state | Supplies expected infrastructure configuration. | No | Yes |

Your Terraform files and state come from **your own Terraform project**, not from DriftCTL. For example, if your infrastructure project is in `C:\work\platform-infra` or `~/work/platform-infra`, that is the directory DriftCTL will inspect.

> [!IMPORTANT]
> DriftCTL reads state Terraform can already read. It does not run `terraform init`, `terraform plan`, `terraform apply`, `terraform refresh`, or `terraform destroy`. Before a live scan, confirm that `terraform show -json` works in the Terraform directory you want to inspect.

## 2. Command Reference

| Command | Purpose | When to use it |
| --- | --- | --- |
| `driftctl init` | Interactively creates a non-secret `driftctl.toml` in the current Terraform directory. | First live scan. |
| `driftctl scan` | Scans using `driftctl.toml` in the current Terraform directory. | Normal, repeatable live use. |
| `driftctl scan --expected <file> --live <file> --report <path> --audit <path>` | Compares two local fixture files without AWS. | Safe offline evaluation. |
| `driftctl scan --terraform-dir <path> --profile <profile> --region <region> --report <path> --audit <path>` | Supplies live-scan options directly. | One-off scans or testing configuration before saving it. |
| `driftctl scan --fail-on severe` | Returns exit code `2` only when a `SEVERE` or `CRITICAL` finding exists. | CI/CD and team alerting policies. |
| `terraform show -json` | Confirms Terraform can read the currently applied state. | Before a first live scan or while troubleshooting state access. |
| `aws sts get-caller-identity --profile <profile>` | Confirms a selected AWS identity is available. | Before a first live scan or while troubleshooting credentials. |

> [!NOTE]
> Angle-bracket values such as `<profile>` and `<path>` are **placeholders**. Replace each with the matching path, AWS profile, Region, or file on your system.

## 3. Install Required Tools

Install Python 3.11 or later, `pipx`, Terraform, and AWS CLI before installing DriftCTL. Git is optional unless you want a source checkout or repository examples. Use an administrator-approved install method on managed devices.

<details>
<summary><strong>Windows</strong></summary>

Open **PowerShell** or the integrated PowerShell terminal in VS Code. The following commands use Windows Package Manager (`winget`); run them one at a time. Restart the terminal after installation so its `PATH` updates.

```powershell
winget install --id Python.Python.3.11 -e --source winget
```

```powershell
py -3 -m pip install --user pipx
```

```powershell
py -3 -m pipx ensurepath
```

```powershell
winget install --id Hashicorp.Terraform -e --source winget
```

```powershell
winget install --id Amazon.AWSCLI -e --source winget
```

</details>

<details>
<summary><strong>macOS</strong></summary>

Open Terminal or the integrated terminal in VS Code. With [Homebrew](https://brew.sh/) installed, run these commands one at a time:

```bash
brew install python
```

```bash
brew install pipx
```

```bash
brew install hashicorp/tap/terraform
```

```bash
brew install awscli
```

</details>

<details>
<summary><strong>Linux (Ubuntu or Debian)</strong></summary>

Open a terminal or the integrated terminal in VS Code. These commands install Python tooling and the AWS CLI. Follow HashiCorp's [official Terraform install instructions](https://developer.hashicorp.com/terraform/install) if your distribution differs from Ubuntu or Debian.

```bash
sudo apt update
```

```bash
sudo apt install -y python3 python3-pip pipx curl unzip gpg
```

```bash
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
```

```bash
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(. /etc/os-release && echo \"$VERSION_CODENAME\") main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
```

```bash
sudo apt update && sudo apt install -y terraform
```

```bash
curl -fsSL https://awscli.amazonaws.com/v2/install.sh | sudo bash -s -- --system
```

</details>

### Verify the tools

Run each command separately in your chosen terminal.

**Windows PowerShell**

```powershell
py -3 --version
```

**macOS or Linux (Bash/Zsh)**

```bash
python3 --version
```

```powershell
terraform --version
```

```powershell
aws --version
```

> [!WARNING]
> Do not continue if Python reports a version older than 3.11. Install a supported Python version, then open a new terminal and verify it again. Do not run Windows-only `py` commands in macOS or Linux terminals.

## 4. Install DriftCTL

After installing `pipx`, close and reopen your terminal so its `PATH` includes the `pipx` application directory. Then install DriftCTL without cloning this repository:

```bash
pipx install drift-ctl
```

```bash
driftctl --help
```

`pipx` keeps DriftCTL and its Python dependencies isolated from your Terraform project. Do not run `driftctl scan` yet; first prepare read-only AWS access and a Terraform project in the next sections.

### Install from source (optional)

Use this only when contributing, developing DriftCTL, or running repository examples directly. Clone the source, create a Python 3.11+ virtual environment, activate it, then run `python -m pip install -e ".[dev]"`. Contributors should follow [CONTRIBUTING.md](../CONTRIBUTING.md).

## 5. Prepare AWS Read-Only Access

Complete this section before either live-scan option in the next section. DriftCTL needs an AWS identity that can list and describe supported resources. It must be separate from the administrative identity that applies Terraform.

1. In AWS IAM, create or choose a dedicated identity such as `driftctl-readonly`.
2. Create a customer-managed policy from [`infra/iam/driftctl-read-only-policy.json`](../infra/iam/driftctl-read-only-policy.json). If you need a small disposable test environment, the identical policy is also in [`examples/live-usage/driftctl-read-only-policy.json`](../examples/live-usage/driftctl-read-only-policy.json).
3. Attach the policy to the dedicated scanning identity.
4. Configure AWS CLI access using your organization's approved method: IAM Identity Center/SSO, an assumed role, environment credentials, or a shared profile.

> [!WARNING]
> Do not use administrator credentials for scanning. Do not add `Create`, `Update`, `Delete`, `Put`, `Attach`, `Detach`, `PassRole`, or Terraform permissions to the DriftCTL scanning identity.

### Choose an AWS CLI credential method

Choose one approved path before running any command below. Do not start the SSO setup unless your organization uses IAM Identity Center.

<details>
<summary><strong>Option A: IAM Identity Center (SSO) - preferred when your organization provides it</strong></summary>

Obtain your organization's **AWS access portal URL** and **SSO Region** first. An AWS administrator can find the portal URL in the AWS Console under **IAM Identity Center** > **Settings** > **AWS access portal URL**. It usually looks like `https://d-xxxxxxxxxx.awsapps.com/start`; it is not the normal AWS Console URL. If you are not an AWS administrator, ask the person who manages IAM Identity Center for these values and for a read-only role assignment.

```powershell
aws configure sso --profile driftctl-readonly
```

Complete the prompts as follows:

| AWS CLI prompt | What to enter |
| --- | --- |
| `SSO session name` | A local label such as `driftctl-sso`. It does not create an AWS resource. |
| `SSO start URL` | Paste your organization's AWS access portal URL. |
| `SSO region` | The Region where your organization enabled IAM Identity Center. This can differ from the Region that holds your infrastructure. |
| `SSO registration scopes` | Press Enter to accept `sso:account:access` unless your administrator gives a different value. |
| Account and role | Select the account and dedicated read-only role or permission set assigned to you. |
| CLI default client Region | Select the Region containing the infrastructure you want DriftCTL to scan. |
| CLI default output format | Press Enter for the default, or choose `json`. |

```powershell
aws sso login --profile driftctl-readonly
```

</details>

<details>
<summary><strong>Option B: Dedicated shared AWS CLI profile - common for personal or learning accounts</strong></summary>

Use this only when your account uses programmatic IAM-user credentials and your organization permits access keys. Run:

Before running it, obtain the credentials from **AWS Console** > **IAM** > **Users** > select the dedicated read-only user > **Security credentials** > **Access keys** > **Create access key**. Select **Command Line Interface (CLI)**, then copy the access key ID and secret access key when AWS displays them. AWS shows the secret access key only once.

```bash
aws configure --profile driftctl-readonly
```

Complete the prompts as follows:

| AWS CLI prompt | What to enter |
| --- | --- |
| `AWS Access Key ID [None]:` | The access key ID you just created for the dedicated read-only IAM user. |
| `AWS Secret Access Key [None]:` | The matching secret access key. The terminal does not echo it while you type. |
| `Default region name [None]:` | The AWS Region containing the Terraform-managed infrastructure you will scan. |
| `Default output format [None]:` | `json`, or press Enter for the AWS CLI default. |

Enter credentials for the **dedicated read-only IAM identity** from this section, not your administrator identity. Treat the access key and secret access key as private credentials: never share them, do not put them in Git, chat messages, or `driftctl.toml`, and make sure they are not visible in recordings or screenshots.

</details>

<details>
<summary><strong>Option C: Existing approved profile or assumed role</strong></summary>

If your organization already configured a read-only AWS CLI profile or role on this machine, do not run either configuration command above. Use that profile name in `driftctl.toml`, then verify it below.

</details>

After completing the one option that applies to you, verify the identity. This works in PowerShell, Bash, and Zsh:

```powershell
aws sts get-caller-identity --profile driftctl-readonly
```

> [!IMPORTANT]
> `driftctl-readonly` is an example profile name. **Placeholder: replace it with the name of your own read-only AWS CLI profile everywhere it appears in this guide.**

> [!NOTE]
> VS Code uses the same credentials as the terminal from which you launched it. Open its integrated terminal after configuring your AWS profile, or restart VS Code if it was already open.

## 6. Choose Your First Scan

Choose one path below. Each one is independent; expand only the path you need.

<details>
<summary><strong>Option A: Try DriftCTL without AWS</strong></summary>

This credential-free demonstration uses repository fixtures. It is useful for learning terminal output, reports, audit evidence, severity, and remediation guidance.

From the DriftCTL repository root, run:

```powershell
driftctl scan --expected examples\expected.json --live examples\live.json --report reports\offline-drift-report.md --audit audit\offline-events.jsonl
```

The included fixtures deliberately produce seven findings. The command writes a report and audit log, then returns exit code `2` because drift was found. That is the expected demonstration result, not an installation failure.

</details>

<details>
<summary><strong>Option B: Use the included disposable live example</strong></summary>

Use this only if you do not have Terraform infrastructure available, or cannot safely scan an existing environment. The sample files are:

- [`examples/live-usage/driftctl-example-security-group.tf`](../examples/live-usage/driftctl-example-security-group.tf)
- [`examples/live-usage/driftctl-read-only-policy.json`](../examples/live-usage/driftctl-read-only-policy.json)

The Terraform sample creates an isolated VPC and a closed, unattached security group. It creates no compute, NAT gateway, load balancer, public IP address, or other hourly-billed resource. It is still an AWS change, so use a non-production account and destroy it when finished.

You need two **different credential pairs** for this option:

| Local AWS CLI profile | Identity and purpose |
| --- | --- |
| `your-terraform-admin-profile` | An approved administrative IAM user or role that Terraform can use to create and later remove the example VPC and security group. This is a placeholder profile name. |
| `driftctl-readonly` | The separate read-only scanning identity prepared in [section 5](#5-prepare-aws-read-only-access). Replace this placeholder with your own scanning-profile name where applicable. |

> [!WARNING]
> Do not run the Terraform commands below with the read-only scanning identity. The two profiles must resolve to different AWS identities. Review the plan before applying it and destroy the sample immediately after testing.

For a complete Ubuntu/Debian example that creates, configures, and verifies both local profiles before this step, see the [Linux quick walkthrough](LINUX_USAGE.md#4-configure-aws-cli-profiles).

Create a folder for the sample outside any source checkout, then download the versioned Terraform file. No repository clone is required.

**Windows PowerShell**

```powershell
New-Item -ItemType Directory -Path "$HOME\driftctl-live-example"
```

```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/heyohjayy/DriftCTL/v1.0.1/examples/live-usage/driftctl-example-security-group.tf" -OutFile "$HOME\driftctl-live-example\main.tf"
```

```powershell
cd "$HOME\driftctl-live-example"
```

**macOS or Linux (Bash/Zsh)**

```bash
mkdir -p ~/driftctl-live-example
```

```bash
curl -fsSLo ~/driftctl-live-example/main.tf https://raw.githubusercontent.com/heyohjayy/DriftCTL/v1.0.1/examples/live-usage/driftctl-example-security-group.tf
```

```bash
cd ~/driftctl-live-example
```

Set your approved administrative Terraform profile, then create the sample.

**Windows PowerShell**

```powershell
$env:AWS_PROFILE = "your-terraform-admin-profile"
```

**macOS or Linux (Bash/Zsh)**

```bash
export AWS_PROFILE="your-terraform-admin-profile"
```

> **Important:** `your-terraform-admin-profile` is a **placeholder**. Replace it with the name of your own approved administrative AWS profile. Do not use `driftctl-readonly` here.

Before continuing, confirm that the selected profile resolves to the approved administrative identity, not the read-only scanning identity:

```powershell
aws sts get-caller-identity --profile "your-terraform-admin-profile"
```

```bash
aws sts get-caller-identity --profile "your-terraform-admin-profile"
```

> [!IMPORTANT]
> Replace `your-terraform-admin-profile` in these commands with your real administrative profile name. The returned ARN must identify the administrative IAM user or role. If it identifies your read-only scanning user, stop and configure this profile again with the administrative identity's credentials before running Terraform.

```powershell
terraform init
```

```powershell
terraform plan -var="aws_region=us-east-1" -out=driftctl-live-example.tfplan
```

```powershell
terraform show -no-color driftctl-live-example.tfplan
```

```powershell
terraform apply driftctl-live-example.tfplan
```

> [!NOTE]
> If Terraform reports `Saved plan is stale`, do not reuse that plan file. Generate a new plan with the same `terraform plan` command, review it with `terraform show`, then apply only the newly generated plan. A previous failed operation can update local Terraform state metadata even when it created no AWS resources.

> **Important:** `us-east-1` is a **placeholder**. Replace it with the AWS Region where you want to create the disposable example, and use the same Region in its scan configuration below.

Create the non-secret scan configuration in the example directory. This writes `driftctl.toml` without opening an editor:

```bash
driftctl init --profile driftctl-readonly --region us-east-1 --tag Project=DriftCTLExample
```

> **Important:** `driftctl-readonly` and `us-east-1` are **placeholders**. Replace them with your own read-only profile name and the Region you chose for the disposable example. Keep `Project=DriftCTLExample` unchanged for this sample.

Clear the administrative profile variable before scanning so DriftCTL uses the read-only profile configured in `driftctl.toml`.

**Windows PowerShell**

```powershell
Remove-Item Env:AWS_PROFILE
```

**macOS or Linux (Bash/Zsh)**

```bash
unset AWS_PROFILE
```

Remain in the example directory and run the branded command:

```powershell
driftctl scan
```

The first scan should be clean. When you are finished, destroy only this disposable example through a reviewed destroy plan:

```powershell
terraform plan -destroy -var="aws_region=us-east-1" -out=driftctl-live-example-destroy.tfplan
```

```powershell
terraform show -no-color driftctl-live-example-destroy.tfplan
```

```powershell
terraform apply driftctl-live-example-destroy.tfplan
```

> **Important:** `us-east-1` is a **placeholder**. Replace it with the same Region used when you created the disposable example.

</details>

<details>
<summary><strong>Option C: Scan your own Terraform-managed AWS environment (main)</strong></summary>

This is the normal DriftCTL product workflow. Use the Terraform directory that owns the applied state for the AWS environment you want to inspect.

### Confirm Terraform can read the applied state

Open a terminal where `driftctl --help` works, then move to your Terraform project directory.

**Windows PowerShell**

```powershell
cd "C:\path\to\your\terraform-project"
```

```powershell
terraform show -json | Out-Null
```

**macOS or Linux (Bash/Zsh)**

```bash
cd "/path/to/your/terraform-project"
```

```bash
terraform show -json > /dev/null
```

> **Important:** `C:\path\to\your\terraform-project` and `/path/to/your/terraform-project` are **placeholders**. Replace them with the local folder that owns the applied Terraform state for the AWS environment you intend to inspect.

If Terraform cannot read the state, fix that before continuing. For a remote backend, use the same approved backend authentication you normally use with Terraform.

### Add the local scan configuration

From the root of **your Terraform project**, run:

```bash
driftctl init
```

Enter the following when prompted:

| Prompt | What to enter |
| --- | --- |
| `AWS CLI profile` | Your dedicated read-only profile. `driftctl-readonly` is an example name. |
| `AWS Region` | The Region containing the resources you intend to inspect, such as `eu-west-1`. |
| `Optional tag scope` | An exact scope such as `Environment=dev`, or press Enter to scan all supported resources in the Region. |

The command creates a non-secret `driftctl.toml` with `terraform_dir = "."`, report path `driftctl-output/live-report.md`, and audit path `driftctl-output/events.jsonl`.

> **Important:** If you use `tags`, both the Terraform-managed resource and the live AWS resource must have every listed tag. A tag filter is a safety boundary: resources outside it will not be evaluated as drift.

<details>
<summary><strong>Optional: keep local scan evidence out of Git</strong></summary>

This is not required to run DriftCTL. Add these paths to `.gitignore` only if your Terraform project is stored in Git and you do not want local reports or audit logs committed. They can contain account-specific infrastructure details.

```gitignore
driftctl-output/
reports/*.md
audit/*.jsonl
```

</details>

### Run the scan

Remain in your Terraform project directory and run:

```powershell
driftctl scan
```

DriftCTL reads the applied Terraform state, collects supported AWS configuration through read-only APIs, applies any tag scope, compares normalized snapshots, and writes the report and audit log.

### Full-command alternative

Use this only when you do not want a `driftctl.toml` file.

**Windows PowerShell**

```powershell
driftctl scan --terraform-dir "C:\path\to\your\terraform-project" --profile driftctl-readonly --region us-east-1 --tag Environment=dev --report "C:\path\to\your\terraform-project\driftctl-output\live-report.md" --audit "C:\path\to\your\terraform-project\driftctl-output\events.jsonl"
```

**macOS or Linux (Bash/Zsh)**

```bash
driftctl scan --terraform-dir "/path/to/your/terraform-project" --profile driftctl-readonly --region us-east-1 --tag Environment=dev --report "/path/to/your/terraform-project/driftctl-output/live-report.md" --audit "/path/to/your/terraform-project/driftctl-output/events.jsonl"
```

> **Important:** Every path, `driftctl-readonly`, `us-east-1`, and `Environment=dev` in these two commands is a **placeholder**. Replace each with the directory, read-only AWS profile, AWS Region, and optional tag scope for your own environment.

</details>

## 7. Read the Results

<details>
<summary><strong>Understand findings, severity, and exit codes</strong></summary>

| Exit code | Meaning | What to do |
| --- | --- | --- |
| `0` | No findings, or no findings at or above an explicit `--fail-on` threshold. | Review the report and retain evidence according to your process. |
| `1` | The scan could not complete. This includes invalid options, unreadable state, unavailable AWS credentials, and audit-chain integrity failures. | Fix the stated problem. Do not replace or edit an existing audit file to bypass an integrity failure. |
| `2` | Drift was found. The report and audit events were still written successfully. | Review the finding; decide whether Terraform or AWS represents the intended state; use your approved change process. |

> [!NOTE]
> Exit codes are for the shell, CI, and scheduled jobs. DriftCTL does not print them during an ordinary interactive scan because the terminal findings are the useful human-facing result. To inspect the code immediately after a command, use `$LASTEXITCODE` in PowerShell or `echo $?` in Bash/Zsh.

| Drift type | Meaning |
| --- | --- |
| `missing` | Terraform expects a resource that is absent from AWS inventory. |
| `unmanaged` | AWS has an in-scope resource Terraform does not manage. |
| `modified` | Terraform and AWS both identify the resource, but one or more supported settings differ. |

### What a finding tells you

For every finding, DriftCTL shows both the difference and the information needed to decide what should happen next. It does not decide or apply the change for you.

| Finding field | What it means |
| --- | --- |
| **Severity** | The urgency level calculated from the changed resource and setting. |
| **Explanation** | Why DriftCTL identified a difference and why its rule selected that severity. |
| **Changed attributes** | The supported settings that differ. |
| **Expected values** | What Terraform's applied state records. |
| **Current/live values** | What DriftCTL read from AWS. |
| **Security, cost, and availability impact** | Assessed impact where the rule can safely determine one; otherwise it remains `NOT ASSESSED`. |
| **Recommended next action** | A human review action, not an automatic fix. |
| **Remediation plan** | Suggested review steps and the approved-change path. |

### Severity levels

| Severity | Meaning | Typical examples |
| --- | --- | --- |
| `MINOR` | Lower-risk metadata or operational difference. | Tags differ, or log retention increased rather than weakened. |
| `MODERATE` | Meaningful configuration difference requiring review. | A DNS record, Lambda memory setting, or ordinary unmanaged resource differs. |
| `SEVERE` | A missing Terraform-managed resource or a security/availability control may have weakened. | Public RDS access, weakened encryption or deletion protection, an unsafe private route, or an EKS control-plane security change. |
| `CRITICAL` | Immediate high-risk exposure or broad privilege escalation. | Public SSH/RDP or all-port security-group ingress, or IAM administrative access added outside Terraform. |

> [!NOTE]
> Severity is a prioritisation signal, not a substitute for your organisation's incident process. Read the explanation, impacts, expected and live values, and recommended next action together before deciding whether AWS or Terraform is the intended state.

> [!WARNING]
> A DriftCTL finding is evidence for review, not permission for automatic remediation. Decide whether the desired correction belongs in Terraform or AWS, get required approval, and make the change through your approved process.

</details>

## 8. Run Future Scans

Keep the same `driftctl.toml` in your Terraform project, change to that directory, and run:

```powershell
driftctl scan
```

Use a separate report and audit destination per environment. Keep each audit file append-only; DriftCTL checks retained hash-chain history before appending new events. For independent evidence against deletion of an entire local file or its final entries, retain reports and audit artifacts outside the workstation that writes them.

To return code `2` only for severe or critical findings, run:

```powershell
driftctl scan --fail-on severe
```

This does not change the report, audit evidence, or read-only behavior. It is useful for a later Jenkins or GitHub Actions integration.

## 9. Troubleshooting

| Problem | Resolution |
| --- | --- |
| `driftctl` is not recognized | Open a new terminal after `pipx ensurepath`, then run `pipx install drift-ctl`. Use `pipx list` to confirm the installation. |
| Windows blocks `driftctl.exe` | Reinstall with `pipx install --force drift-ctl`. If an enterprise policy blocks the `pipx` launcher, contact the device administrator; the repository development shim applies only to source installations. |
| AWS credentials cannot be found | Verify the profile with `aws sts get-caller-identity --profile <your-profile>`, replacing `<your-profile>` with your actual read-only profile name. Make it match `driftctl.toml`. |
| `Saved plan is stale` | Do not apply the old plan file. Run `terraform plan` again, review the new plan with `terraform show`, then apply only the new plan. A previous failed operation can update local state metadata even when it created no AWS resources. |
| Terraform state cannot be read | Work from the Terraform root that owns the applied state and confirm `terraform show -json` succeeds there. |
| A resource is absent from a scoped scan | Ensure it has every tag in `tags`, both in Terraform state and in AWS. |
| Counts differ but there are no findings | Read collection diagnostics. Unsupported resources and deliberately excluded AWS-managed resources can affect counts without being drift. |

For DriftCTL's own non-production test environments, deliberate drift scenarios, screenshots, and cleanup procedures, see [`docs/VALIDATION.md`](VALIDATION.md).
