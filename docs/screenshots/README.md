# Screenshot Evidence

This visual index contains the sanitized evidence captured while validating DriftCTL. Each entry shows the sequential filename followed by the image itself. The screenshots demonstrate local setup, fixture evaluation, read-only AWS access, controlled drift detection, remediation, and clean post-remediation results.

> [!NOTE]
> Screenshots record validation evidence only. For first-time product use against your own Terraform-managed environment, read [`docs/USAGE.md`](../USAGE.md). For the controlled validation procedures behind this evidence, read [`docs/VALIDATION.md`](../VALIDATION.md).

### 01a - Local Python Environment Setup

`01a-local-environment-setup.png`
![01a-local-environment-setup](01a-local-environment-setup.png)

### 01b - DriftCTL Installation

`01b-local-environment-setup.png`
![01b-local-environment-setup](01b-local-environment-setup.png)

### 02 - Automated Tests Passing

`02-tests-passing.png`
![02-tests-passing](02-tests-passing.png)

### 03a - Offline Drift Summary

`03a-offline-drift-summary.png`
![03a-offline-drift-summary](03a-offline-drift-summary.png)

### 03b - Offline Drift Findings, Middle Section

`03b-offline-drift-findings-middle.png`
![03b-offline-drift-findings-middle](03b-offline-drift-findings-middle.png)

### 03c - Offline Drift Findings, Final Section

`03c-offline-drift-findings-end.png`
![03c-offline-drift-findings-end](03c-offline-drift-findings-end.png)

### 04a - Read-Only AWS Profile Verification

`04a-read-only-profile-verification.png`
![04a-read-only-profile-verification](04a-read-only-profile-verification.png)

### 04b - Clean Scoped Live Baseline

`04b-live-baseline-scan.png`
![04b-live-baseline-scan](04b-live-baseline-scan.png)

### 05 - Minor VPC Tag Drift

`05-minor-tag-drift.png`
![05-minor-tag-drift](05-minor-tag-drift.png)

### 06 - Unmanaged In-Scope Security Group

`06-unmanaged-resource.png`
![06-unmanaged-resource](06-unmanaged-resource.png)

### 07 - Critical Public SSH Drift

`07-critical-security-drift.png`
![07-critical-security-drift](07-critical-security-drift.png)

### 08 - Severe Private Route Drift

`08-severe-private-route-drift.png`
![08-severe-private-route-drift](08-severe-private-route-drift.png)

### 09 - IAM Policy Attachment Drift

`09-iam-policy-drift.png`
![09-iam-policy-drift](09-iam-policy-drift.png)

### 10 - Route 53 Record Drift

`10-route53-record-drift.png`
![10-route53-record-drift](10-route53-record-drift.png)

### 11 - Clean Scan After Initial Remediation

`11-clean-after-remediation.png`
![11-clean-after-remediation](11-clean-after-remediation.png)

### 12 - Application Infrastructure Read-Only Access

`12-sprint3b-readonly-access-verification.png` - the dedicated collector profile reads NAT, Application Load Balancer, and RDS resources.

![12-sprint3b-readonly-access-verification](12-sprint3b-readonly-access-verification.png)

### 13 - Application Infrastructure Clean Baseline

`13-sprint3b-clean-live-baseline.png` - clean baseline after application infrastructure is applied.

![13-sprint3b-clean-live-baseline](13-sprint3b-clean-live-baseline.png)

### 14 - Target Group Health-Check Drift

`14-sprint3b-target-group-drift.png` - target-group health-check drift detected as moderate.

![14-sprint3b-target-group-drift](14-sprint3b-target-group-drift.png)

### 15 - RDS Deletion-Protection Drift

`15-sprint3b-rds-deletion-protection-drift.png` - weakened RDS deletion protection detected as severe.

![15-sprint3b-rds-deletion-protection-drift](15-sprint3b-rds-deletion-protection-drift.png)

### 16 - Private Route Drift

`16-sprint3b-private-route-drift.png` - private default route redirected from NAT to internet gateway and detected as severe.

![16-sprint3b-private-route-drift](16-sprint3b-private-route-drift.png)

### 17 - Application Infrastructure Clean After Remediation

`17-sprint3b-clean-after-remediation.png`
![17-sprint3b-clean-after-remediation](17-sprint3b-clean-after-remediation.png)

### 18 - ECS Fargate Clean Baseline

`18-sprint3c1-ecs-fargate-clean-baseline.png`
![18-sprint3c1-ecs-fargate-clean-baseline](18-sprint3c1-ecs-fargate-clean-baseline.png)

### 19 - CloudWatch Log Retention Drift

`19-sprint3c1-cloudwatch-log-retention-drift.png` - retention changed from seven days to one day and detected as moderate drift.

![19-sprint3c1-cloudwatch-log-retention-drift](19-sprint3c1-cloudwatch-log-retention-drift.png)

### 20 - ECS Service Desired-Count Drift

`20-sprint3c1-ecs-service-desired-count-drift.png` - Fargate service scaled from one task to zero and detected with high availability impact.

![20-sprint3c1-ecs-service-desired-count-drift](20-sprint3c1-ecs-service-desired-count-drift.png)

### 21 - ECS Fargate Clean After Remediation

`21-sprint3c1-ecs-fargate-clean-after-remediation.png`
![21-sprint3c1-ecs-fargate-clean-after-remediation](21-sprint3c1-ecs-fargate-clean-after-remediation.png)

### 22 - ECS on EC2 Clean Baseline

`22-sprint3c1-ecs-ec2-clean-baseline.png`
![22-sprint3c1-ecs-ec2-clean-baseline](22-sprint3c1-ecs-ec2-clean-baseline.png)

### 23 - ECS Capacity-Provider Drift

`23-sprint3c1-ecs-ec2-capacity-provider-drift.png` - target capacity changed from 100 to 90 and detected as moderate drift.

![23-sprint3c1-ecs-ec2-capacity-provider-drift](23-sprint3c1-ecs-ec2-capacity-provider-drift.png)

### 24 - ECS on EC2 Clean After Remediation

`24-sprint3c1-ecs-ec2-clean-after-remediation.png`
![24-sprint3c1-ecs-ec2-clean-after-remediation](24-sprint3c1-ecs-ec2-clean-after-remediation.png)

### 25 - Lambda Clean Baseline

`25-sprint3c2-lambda-clean-baseline.png`
![25-sprint3c2-lambda-clean-baseline](25-sprint3c2-lambda-clean-baseline.png)

### 26 - Lambda Memory Drift

`26-sprint3c2-lambda-memory-drift.png` - memory changed from 128 MB to 256 MB and detected as moderate drift.

![26-sprint3c2-lambda-memory-drift](26-sprint3c2-lambda-memory-drift.png)

### 27 - Lambda Clean After Remediation

`27-sprint3c2-lambda-clean-after-remediation.png`
![27-sprint3c2-lambda-clean-after-remediation](27-sprint3c2-lambda-clean-after-remediation.png)

### 28 - EKS Clean Baseline

`28-sprint3c3-eks-clean-baseline.png`
![28-sprint3c3-eks-clean-baseline](28-sprint3c3-eks-clean-baseline.png)

### 29 - EKS Managed Node-Group Label Drift

`29-sprint3c3-eks-node-group-label-drift.png` - a managed node-group label difference detected as moderate drift.

![29-sprint3c3-eks-node-group-label-drift](29-sprint3c3-eks-node-group-label-drift.png)

### 30 - EKS Clean After Remediation

`30-sprint3c3-eks-clean-after-remediation.png`
![30-sprint3c3-eks-clean-after-remediation](30-sprint3c3-eks-clean-after-remediation.png)
