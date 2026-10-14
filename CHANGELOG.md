# Changelog

All notable DriftCTL changes are documented here. DriftCTL follows semantic versioning for releases.

## 1.0.0

First stable release of the read-only Terraform-to-AWS drift-detection CLI.

### Added

- Terraform-state and live AWS comparison for the supported EC2, S3, IAM, Route 53, Application Load Balancing, RDS, ECS, CloudWatch Logs, Lambda, EventBridge, and EKS resource surfaces.
- Tag-scoped live collection, collection diagnostics, `missing`, `unmanaged`, and `modified` drift detection, conservative risk classification, and human-approved remediation guidance.
- Markdown reports and integrity-protected, hash-chained JSONL audit evidence.
- Exit-code support for manual and future automated use: `0` for a clean scan, `1` for an incomplete scan, and `2` when drift is found.
- First-use documentation, platform-specific installation guidance, an offline fixture demonstration, a disposable live example, controlled validation records, and screenshot evidence.
- Pull-request and main-branch CI for tests, Python compilation, dependency checks, package builds, and whitespace validation.

### Known Limit

- The local audit chain detects alterations to retained history, but an independently retained artifact or checkpoint is required to detect deletion of an entire audit file or its final entries. That external retention belongs in the planned automation release.

### Safety

- DriftCTL does not run Terraform mutation commands, change Terraform state, or call AWS mutation APIs.
- Live collection is designed for a separately configured least-privilege read-only AWS identity.

## Unreleased

- Jenkins and optional GitHub Actions drift-monitoring runners are planned for the next release line. They will not introduce automatic remediation.
