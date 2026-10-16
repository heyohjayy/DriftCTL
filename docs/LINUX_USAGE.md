# DriftCTL Linux Quick Walkthrough

This is a copy-ready Linux walkthrough for a first DriftCTL live scan. It uses:

- a dedicated AWS CLI profile named `driftctl-readonly` for DriftCTL;
- a separate administrative AWS CLI profile named `driftctl-terraform-admin` only to create and later remove a small disposable Terraform example; and
- Ubuntu or Debian commands. For another Linux distribution, install equivalent packages first.

The walkthrough creates an isolated VPC and a closed, unattached security group. It creates no compute, NAT gateway, load balancer, or public IP address. The scan itself is read-only. Still, every Terraform command changes AWS, so use a non-production AWS account and remove the sample as soon as the demonstration is complete.

> [!WARNING]
> Never use the administrative Terraform profile as DriftCTL's scanning profile. Do not place access keys or secret keys in this document, Git, `driftctl.toml`, recordings, screenshots, or chat messages.

## What You Need

Before starting, have:

1. An AWS account where you are permitted to create IAM policies and users, plus a separate administrative profile permitted to create and delete a VPC and security group.
2. An AWS Region to use for this demonstration. This guide uses `eu-west-1` (Ireland); choose another supported Region if needed, then use that same Region everywhere below.
3. An Ubuntu or Debian terminal. Run each code block separately and wait for it to finish before moving to the next one.

> [!IMPORTANT]
> Names such as `driftctl-readonly` and `driftctl-terraform-admin` are example AWS CLI profile names. Keep them if you want the commands to work exactly as written, or replace every occurrence with your own profile names.

## 1. Install the Required Tools

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
sudo apt update
```

```bash
sudo apt install -y terraform
```

```bash
curl -fsSL https://awscli.amazonaws.com/v2/install.sh | sudo bash -s -- --system
```

Verify each tool. Python must be version 3.11 or later.

```bash
python3 --version
```

```bash
terraform --version
```

```bash
aws --version
```

## 2. Install DriftCTL

Install DriftCTL with `pipx`. This creates an isolated Python environment for the command; it does not clone this repository or require you to create a virtual environment.

```bash
pipx ensurepath
```

```bash
export PATH="$HOME/.local/bin:$PATH"
```

```bash
pipx install drift-ctl
```

```bash
driftctl --help
```

> [!NOTE]
> Do not run `driftctl scan` yet. It needs a configured Terraform project. This walkthrough creates and configures a disposable project next.

## 3. Create the Dedicated Read-Only AWS Identity

In the AWS Console, open **IAM**. Create a customer-managed policy named `DriftCTLReadOnly`, select the JSON editor, and paste the policy shown below. Save it. Then open **Users**, create or choose an IAM user named `driftctl-readonly`, and attach the `DriftCTLReadOnly` policy to that user.

<details>
<summary><strong>Copy the disposable example read-only IAM policy</strong></summary>

This is the same file as [`examples/live-usage/driftctl-read-only-policy.json`](../examples/live-usage/driftctl-read-only-policy.json). It contains read-only AWS inventory permissions only.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DescribeEc2Inventory",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeInternetGateways",
        "ec2:DescribeNatGateways",
        "ec2:DescribeRouteTables",
        "ec2:DescribeNetworkAcls"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DescribeApplicationLoadBalancing",
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:DescribeListeners",
        "elasticloadbalancing:DescribeLoadBalancers",
        "elasticloadbalancing:DescribeRules",
        "elasticloadbalancing:DescribeTags",
        "elasticloadbalancing:DescribeTargetGroups"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DescribeRdsInventory",
      "Effect": "Allow",
      "Action": [
        "rds:DescribeDBInstances",
        "rds:ListTagsForResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DescribeEcsInventory",
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeCapacityProviders",
        "ecs:DescribeClusters",
        "ecs:DescribeServices",
        "ecs:DescribeTaskDefinition",
        "ecs:ListClusters",
        "ecs:ListServices",
        "ecs:ListTagsForResource",
        "ecs:ListTaskDefinitions"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DescribeCloudWatchLogsInventory",
      "Effect": "Allow",
      "Action": [
        "logs:DescribeLogGroups",
        "logs:ListTagsForResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ReadLambdaInventory",
      "Effect": "Allow",
      "Action": [
        "lambda:GetFunctionConcurrency",
        "lambda:ListFunctions",
        "lambda:ListTags"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ReadEventBridgeInventory",
      "Effect": "Allow",
      "Action": [
        "events:ListRules",
        "events:ListTagsForResource",
        "events:ListTargetsByRule"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ReadEksInventory",
      "Effect": "Allow",
      "Action": [
        "eks:DescribeCluster",
        "eks:DescribeNodegroup",
        "eks:ListClusters",
        "eks:ListNodegroups"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ReadIamIdentityInventory",
      "Effect": "Allow",
      "Action": [
        "iam:GetInstanceProfile",
        "iam:GetRole",
        "iam:GetRolePolicy",
        "iam:ListAttachedRolePolicies",
        "iam:ListInstanceProfiles",
        "iam:ListInstanceProfileTags",
        "iam:ListRolePolicies",
        "iam:ListRoles",
        "iam:ListRoleTags"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ReadRoute53Inventory",
      "Effect": "Allow",
      "Action": [
        "route53:ListHostedZones",
        "route53:ListResourceRecordSets",
        "route53:ListTagsForResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ListS3Buckets",
      "Effect": "Allow",
      "Action": "s3:ListAllMyBuckets",
      "Resource": "*"
    },
    {
      "Sid": "ReadS3BucketControls",
      "Effect": "Allow",
      "Action": [
        "s3:GetEncryptionConfiguration",
        "s3:GetBucketPublicAccessBlock",
        "s3:GetBucketTagging"
      ],
      "Resource": "arn:aws:s3:::*"
    }
  ]
}
```

</details>

> [!WARNING]
> AWS displays a secret access key only once. Store it only through your approved credential process. Do not reveal it on screen or include it in a recording.

## 4. Configure AWS CLI Profiles

You must configure and verify **both** profiles in this section before moving to Terraform:

| Profile | Purpose | Used by |
| --- | --- | --- |
| `driftctl-readonly` | Inspects live AWS resources without changing them. | `driftctl scan` |
| `driftctl-terraform-admin` | Creates and destroys only the disposable VPC and security-group example. | Terraform commands in steps 5 and 8 |

> [!IMPORTANT]
> Configuring `driftctl-readonly` does **not** create `driftctl-terraform-admin`. They need different credentials and are configured separately. Do not continue to `terraform plan` until both `aws sts get-caller-identity` checks below return successfully.

<details>
<summary><strong>Configure the read-only scanning profile</strong></summary>

First create an access key for the dedicated **read-only** IAM user: **AWS Console** > **IAM** > **Users** > `driftctl-readonly` > **Security credentials** > **Access keys** > **Create access key**. Select **Command Line Interface (CLI)**, continue, then copy the access key ID and secret access key when AWS displays them.

Now configure the read-only AWS CLI profile:

```bash
aws configure --profile driftctl-readonly
```

Complete the prompts exactly as follows:

| AWS CLI prompt | What to enter |
| --- | --- |
| `AWS Access Key ID [None]:` | The access key ID you just created for `driftctl-readonly`. |
| `AWS Secret Access Key [None]:` | The matching secret access key. The terminal does not echo it while you type. |
| `Default region name [None]:` | `eu-west-1` |
| `Default output format [None]:` | `json` |

Confirm that it works. The command should return the account and ARN for the dedicated read-only identity.

```bash
aws sts get-caller-identity --profile driftctl-readonly
```

The returned ARN should identify the dedicated read-only IAM user, such as `:user/driftctl-readonly`.

</details>

<details>
<summary><strong>Configure the Terraform administration profile</strong></summary>

This second profile is required before Terraform can create or destroy the disposable sample. Use an approved **non-root** IAM user or role; never create access keys for the AWS account root user. If you need an access key for an approved IAM user, obtain it through **AWS Console** > **IAM** > **Users** > select that approved administrative user > **Security credentials** > **Access keys** > **Create access key**, then select **Command Line Interface (CLI)**.

Do not use the read-only access key here.

```bash
aws configure --profile driftctl-terraform-admin
```

Complete the prompts as follows:

| AWS CLI prompt | What to enter |
| --- | --- |
| `AWS Access Key ID [None]:` | The access key ID for your approved non-root administrative IAM user. |
| `AWS Secret Access Key [None]:` | The matching secret access key. The terminal does not echo it while you type. |
| `Default region name [None]:` | `eu-west-1` |
| `Default output format [None]:` | `json` |

Confirm the administrative profile separately.

```bash
aws sts get-caller-identity --profile driftctl-terraform-admin
```

The returned ARN must identify your separate administrative IAM user or role. It must **not** end with `:user/driftctl-readonly`.

Do not continue until both identity commands have returned successfully. If the second command says the profile does not exist, rerun `aws configure --profile driftctl-terraform-admin` and complete its four prompts with the approved administrative user's credentials.

</details>

## 5. Create the Disposable Terraform Example

Create the example project outside the DriftCTL repository.

The `-p` flag means "create parent directories if necessary, and do not report an error if the directory already exists."

```bash
mkdir -p ~/driftctl-live-example
```

```bash
cd ~/driftctl-live-example
```

Choose **one** of the following ways to create `main.tf`. Do not do both. Option B is the recommended copy-ready path for this walkthrough.

<details>
<summary><strong>Option A: Copy the Terraform file manually</strong></summary>

This is the same file as [`examples/live-usage/driftctl-example-security-group.tf`](../examples/live-usage/driftctl-example-security-group.tf). Create a file named `main.tf` in `~/driftctl-live-example`, paste the content below, then save it. Its generic `us-east-1` default is overridden by the explicit `eu-west-1` Terraform plan command in the next step.

```hcl
terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

variable "aws_region" {
  description = "AWS Region in which to create this disposable DriftCTL example."
  type        = string
  default     = "us-east-1"
}

provider "aws" {
  region = var.aws_region
}

# This isolated VPC and unattached security group have no hourly AWS charge.
# Keep the security group closed: it has no ingress or egress rules.
resource "aws_vpc" "driftctl_example" {
  cidr_block           = "10.254.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name    = "driftctl-example-vpc"
    Project = "DriftCTLExample"
    Purpose = "read-only-drift-scan-demo"
  }
}

resource "aws_security_group" "driftctl_example" {
  name                   = "driftctl-example-closed-sg"
  description            = "Closed, unattached security group for a DriftCTL example"
  vpc_id                 = aws_vpc.driftctl_example.id
  revoke_rules_on_delete = true
  ingress                = []
  egress                 = []

  tags = {
    Name    = "driftctl-example-closed-sg"
    Project = "DriftCTLExample"
    Purpose = "read-only-drift-scan-demo"
  }
}

output "driftctl_example_vpc_id" {
  value = aws_vpc.driftctl_example.id
}

output "driftctl_example_security_group_id" {
  value = aws_security_group.driftctl_example.id
}
```

</details>

<details>
<summary><strong>Option B: Download the versioned Terraform example (recommended)</strong></summary>

This command downloads the exact same `main.tf` file shown in Option A from the matching DriftCTL release. Use it instead of manually copying the code above.

```bash
curl -fsSLo ./main.tf https://raw.githubusercontent.com/heyohjayy/DriftCTL/v1.0.1/examples/live-usage/driftctl-example-security-group.tf
```

</details>

Set the administrative profile for Terraform. This affects this terminal only.

```bash
export AWS_PROFILE="driftctl-terraform-admin"
```

```bash
terraform init
```

```bash
terraform plan -var="aws_region=eu-west-1" -out=driftctl-live-example.tfplan
```

Review the plan. It should add only one VPC and one closed security group.

```bash
terraform show -no-color driftctl-live-example.tfplan
```

Apply the reviewed plan.

```bash
terraform apply driftctl-live-example.tfplan
```

> [!NOTE]
> If an apply fails and Terraform later reports `Saved plan is stale`, do not retry the old plan file. Run `terraform plan` again, review the new plan with `terraform show`, then apply the newly saved plan. A failed operation can update local Terraform state metadata even when AWS created no resource.

> [!IMPORTANT]
> `eu-west-1` is the Region used by this walkthrough. If you choose another Region, replace every `eu-west-1` in this walkthrough with your chosen Region before creating the sample.

## 6. Configure DriftCTL for the Example

Create the non-secret scan configuration in the disposable Terraform directory. `driftctl init` writes `driftctl.toml` automatically; it does not store AWS credentials or make AWS changes. In this command, `--profile` selects the dedicated read-only AWS CLI profile, `--region` selects the AWS Region to scan, and `--tag` limits the scan to resources tagged `Project=DriftCTLExample`.

```bash
driftctl init --profile driftctl-readonly --region eu-west-1 --tag Project=DriftCTLExample
```

> [!IMPORTANT]
> `driftctl-readonly` and `eu-west-1` are example values. Replace them if you chose a different read-only AWS profile or Region. Keep `Project=DriftCTLExample` unchanged for this sample.

The generated file tells future `driftctl scan` commands to read Terraform state from this directory, use the read-only profile and Region above, and write the Markdown report plus hash-chained audit log under `driftctl-output/`. You do not need to edit the file for this walkthrough.

## 7. Run the Read-Only Scan

Clear the administrative Terraform profile so the terminal has no administrative default, then run the normal DriftCTL product command. DriftCTL reads `aws_profile = "driftctl-readonly"` from `driftctl.toml` and uses that separate read-only identity.

```bash
unset AWS_PROFILE
```

```bash
driftctl scan
```

The baseline should show `0` findings and `No drift detected`. DriftCTL writes these two local evidence files:

- `~/driftctl-live-example/driftctl-output/live-report.md`
- `~/driftctl-live-example/driftctl-output/events.jsonl`

## 8. Destroy the Disposable Example

Do this promptly after recording the clean scan. The AWS CLI profile below is the administrative Terraform profile, not the read-only profile.

```bash
export AWS_PROFILE="driftctl-terraform-admin"
```

```bash
terraform plan -destroy -var="aws_region=eu-west-1" -out=driftctl-live-example-destroy.tfplan
```

Review the plan. It should destroy only the VPC and security group created by this walkthrough.

```bash
terraform show -no-color driftctl-live-example-destroy.tfplan
```

```bash
terraform apply driftctl-live-example-destroy.tfplan
```

Confirm the local Terraform state no longer contains the disposable resources.

```bash
terraform state list
```

The command should return no resources. DriftCTL remains installed through `pipx`; you can reuse it later with a different Terraform project and a read-only profile.

## Next Steps: Scan Your Own Environment

This walkthrough is a disposable proof that DriftCTL is installed and can compare Terraform state with live AWS. It does **not** scan the infrastructure you actually manage. After the teardown succeeds, use the same installed `driftctl` command with your own Terraform project:

1. Change to the root directory that owns your own applied Terraform state.
2. Confirm `terraform show -json` succeeds there.
3. Run `driftctl init`, enter your own dedicated read-only profile, Region, and optional tag scope.
4. Run `driftctl scan` from that same Terraform directory.

For the cross-platform, step-by-step version of this workflow, including how to interpret findings and run future scans, see [Option C in the full Usage Guide](USAGE.md#6-choose-your-first-scan).
