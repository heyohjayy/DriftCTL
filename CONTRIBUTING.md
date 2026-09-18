# Contributing to DriftCTL

Thank you for considering a contribution to DriftCTL. Contributions that make Terraform-to-AWS drift detection clearer, safer, and more useful are welcome.

By submitting a contribution for inclusion in DriftCTL, you agree to license that contribution under the [Apache License 2.0](LICENSE), unless you explicitly state otherwise in writing.

## Useful Contributions

Areas where help is especially valuable include:

- Support for additional AWS resource types through Terraform adapters, read-only AWS collectors, normalization, detection rules, and tests.
- Severity, impact, explanation, and remediation policies that remain conservative when the available data cannot establish risk reliably.
- Test fixtures and regression tests for Terraform-state or AWS-inventory edge cases.
- Documentation improvements, including setup guidance, production scanning guidance, and sanitized validation evidence.
- Non-production validation infrastructure that is short-lived, cost-aware, and easy to clean up.

## Before You Start

Open or review an issue before beginning a substantial change so the scope and intended behavior are clear. Do not include AWS credentials, Terraform state, private infrastructure details, or unredacted screenshots in an issue, branch, commit, or pull request.

DriftCTL is strictly read-only. Contributions must not add AWS mutation APIs or make DriftCTL run `terraform init`, `terraform plan`, `terraform apply`, or `terraform refresh`.

## Development Workflow

1. Fork the repository and clone your fork:

   ```bash
   git clone https://github.com/<your-username>/DriftCTL.git
   cd DriftCTL
   ```

2. Create a focused branch:

   ```bash
   git switch -c feature/short-description
   ```

3. Create and activate a Python virtual environment. Follow the terminal-specific instructions in the [setup guide](docs/SETUP.md).

4. Install the project and development dependencies:

   ```bash
   python -m pip install -e ".[dev]"
   ```

5. Make the smallest change that solves the stated problem. Keep provider-specific parsing in adapters and keep comparison logic independent of raw Terraform or boto3 response formats.

6. Add or update tests for every behavior change. Run the full suite:

   ```bash
   python -m pytest
   ```

7. Check the working tree for whitespace errors:

   ```bash
   git diff --check
   ```

## AWS and Terraform Safety

Use only a personal, learning, or non-production AWS environment for live validation. Apply the repository's least-privilege [read-only IAM policy](infra/iam/driftctl-read-only-policy.json) to the identity used by DriftCTL.

Terraform actions and any controlled drift changes must be performed separately, with an approved administrative identity. Before creating chargeable resources, review `terraform plan`; after validation, restore the intended state and destroy temporary resources.

## Pull Requests

Before opening a pull request:

- Explain the problem and the behavior your change adds or corrects.
- Include relevant test results.
- Update documentation when a user-facing workflow, supported resource type, or configuration option changes.
- Keep commits focused and use clear, descriptive commit messages.
- Do not include generated reports, audit logs, Terraform plans, credentials, or private infrastructure data.

Thank you for helping make DriftCTL safer and more dependable.
