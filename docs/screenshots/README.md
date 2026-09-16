# Screenshot Evidence

This directory holds the sanitized evidence screenshots used in the project README and setup guide.

- `01a-local-environment-setup.png`
- `01b-local-environment-setup.png`
- `02-tests-passing.png`
- `03a-offline-drift-summary.png`
- `03b-offline-drift-findings-middle.png`
- `03c-offline-drift-findings-end.png`
- `04a-read-only-profile-verification.png`
- `04b-live-baseline-scan.png`
- `05-minor-tag-drift.png`
- `06-unmanaged-resource.png`
- `07-critical-security-drift.png`
- `08-severe-private-route-drift.png`
- `09-iam-policy-drift.png`
- `10-route53-record-drift.png`
- `11-clean-after-remediation.png`
- `12-sprint3b-readonly-access-verification.png`: dedicated collector profile reads NAT, Application Load Balancer, and RDS resources.
- `13-sprint3b-clean-live-baseline.png`: clean live baseline after application infrastructure is applied.
- `14-sprint3b-target-group-drift.png`: target-group health-check drift detected as moderate.
- `15-sprint3b-rds-deletion-protection-drift.png`: weakened RDS deletion protection detected as severe.
- `16-sprint3b-private-route-drift.png`: private default route redirected from NAT to internet gateway and detected as severe.
- `17-sprint3b-clean-after-remediation.png`: final clean scan after application-infrastructure remediation.
- `18-sprint3c1-ecs-fargate-clean-baseline.png`: clean baseline after the ECS Fargate validation environment is applied.
- `19-sprint3c1-cloudwatch-log-retention-drift.png`: CloudWatch log retention changed from seven days to one day and detected as moderate drift.
- `20-sprint3c1-ecs-service-desired-count-drift.png`: Fargate service scaled from one task to zero and detected with high availability impact.
- `21-sprint3c1-ecs-fargate-clean-after-remediation.png`: final clean scan after the ECS service and CloudWatch Logs settings are restored.

These screenshots document local setup, automated tests, an intentional offline demonstration, read-only AWS access, clean live baselines, controlled drift across networking, IAM, Route 53, load balancing, RDS, ECS, and CloudWatch Logs, plus successful final remediation scans.
