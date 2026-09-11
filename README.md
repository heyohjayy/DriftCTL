# Infrastructure Drift Control Platform

`driftctl` is a read-only drift engine for comparing Terraform state with AWS inventory. It is designed for an operational workflow: identify divergence, classify its risk, recommend a safe next action, and retain an append-only decision trail.

Sprint 2 adds real collection while preserving the local workflow. The Terraform CLI loader and AWS collector feed the same provider-neutral adapters used by JSON fixtures. No command invokes Terraform apply, writes Terraform state, or calls AWS mutation APIs.

## Quick start

Python 3.11+ is required.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
driftctl scan --expected examples/expected.json --live examples/live.json --report reports/drift-report.md --audit audit/events.jsonl
```

The command writes a Markdown report and appends JSONL audit events. This offline path remains credential-free and is the best starting point for development and CI.

For a complete newcomer-oriented walkthrough, including safe live AWS testing and screenshot guidance, read [the setup and usage guide](docs/SETUP.md).

## Safe AWS demo

Use an initialized Terraform working directory with access to the state you intend to inspect. The loader runs only `terraform show -json`; it does not run `init`, `plan`, `apply`, or `refresh`.

Attach [the supplied read-only IAM policy](infra/iam/driftctl-read-only-policy.json) to the collecting principal or assumed role. When using `--role-arn`, the source principal also needs a narrowly scoped `sts:AssumeRole` permission for that role. Copy [the sample environment file](examples/aws-demo.env.example) as a reference for the values; do not store AWS credentials in it.

```powershell
driftctl scan `
  --terraform-dir infra/terraform `
  --profile driftctl-readonly `
  --region us-east-1 `
  --role-arn arn:aws:iam::123456789012:role/driftctl-readonly `
  --report reports/aws-drift-report.md `
  --audit audit/events.jsonl
```

`--expected` and `--terraform-dir` are mutually exclusive. Supplying `--live` keeps the scan offline; omitting it enables AWS collection and requires an explicit `--region`. The collector uses only `Describe`, `List`, and `Get` APIs for EC2, security groups, and S3 bucket controls.

## Design

The source adapters translate Terraform `terraform show -json`-style data and boto3 response-shaped data into `ResourceSnapshot` objects. The detector compares only those shared models and emits exactly `missing`, `unmanaged`, or `modified` findings. Severity policies are independent rules evaluated after detection, so policies can be changed without modifying the comparison loop.

Supported in Sprint 2:

- AWS security groups / VPC networking
- S3 buckets, public-access blocks, and default encryption
- EC2 instances

See `docs/architecture.md` for the flow and `infra/terraform` for sample managed infrastructure.
