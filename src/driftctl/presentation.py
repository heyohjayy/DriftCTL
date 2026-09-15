"""Read-only operational guidance policies for rendered drift findings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from driftctl.models import DriftType, Finding
from driftctl.severity_rules import has_dangerous_ingress


class ImpactLevel(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"
    NONE = "NONE"
    NOT_ASSESSED = "NOT ASSESSED"


@dataclass(frozen=True)
class ImpactAssessment:
    security: ImpactLevel
    cost: ImpactLevel
    availability: ImpactLevel


@dataclass(frozen=True)
class FindingExplanation:
    change: str
    consequence: str


@dataclass(frozen=True)
class RemediationPlan:
    recommended_action: str
    actions: tuple[str, ...]


class ImpactRule(Protocol):
    def evaluate(self, finding: Finding) -> ImpactAssessment | None: ...


class ExplanationRule(Protocol):
    def evaluate(self, finding: Finding) -> FindingExplanation | None: ...


class RemediationRule(Protocol):
    def evaluate(self, finding: Finding) -> RemediationPlan | None: ...


class PublicIngressImpactRule:
    def evaluate(self, finding: Finding) -> ImpactAssessment | None:
        snapshot = finding.live or finding.expected
        if snapshot and has_dangerous_ingress(snapshot.attributes.get("ingress", [])):
            return ImpactAssessment(ImpactLevel.HIGH, ImpactLevel.NONE, ImpactLevel.LOW)
        return None


class TagOnlyImpactRule:
    def evaluate(self, finding: Finding) -> ImpactAssessment | None:
        if finding.drift_type is DriftType.MODIFIED and set(finding.changes) <= {"tags"}:
            return ImpactAssessment(ImpactLevel.LOW, ImpactLevel.NONE, ImpactLevel.NONE)
        return None


class PublicRdsImpactRule:
    def evaluate(self, finding: Finding) -> ImpactAssessment | None:
        if finding.identity.resource_type == "rds_db_instance" and finding.live and finding.live.attributes.get("publicly_accessible"):
            return ImpactAssessment(ImpactLevel.HIGH, ImpactLevel.NONE, ImpactLevel.NOT_ASSESSED)
        return None


class UnassessedImpactRule:
    def evaluate(self, finding: Finding) -> ImpactAssessment:
        return ImpactAssessment(
            ImpactLevel.NOT_ASSESSED,
            ImpactLevel.NOT_ASSESSED,
            ImpactLevel.NOT_ASSESSED,
        )


class PublicIngressExplanationRule:
    def evaluate(self, finding: Finding) -> FindingExplanation | None:
        snapshot = finding.live or finding.expected
        if snapshot and has_dangerous_ingress(snapshot.attributes.get("ingress", [])):
            return FindingExplanation(
                "A security-group ingress rule permits public SSH, RDP, or all-port access.",
                "This can expose administrative access to the internet and should be reviewed urgently.",
            )
        return None


class TagOnlyExplanationRule:
    def evaluate(self, finding: Finding) -> FindingExplanation | None:
        if finding.drift_type is DriftType.MODIFIED and set(finding.changes) <= {"tags"}:
            return FindingExplanation(
                "Only resource tags differ from the Terraform inventory.",
                "Metadata drift can affect ownership, cost allocation, and operational governance.",
            )
        return None


class GenericExplanationRule:
    def evaluate(self, finding: Finding) -> FindingExplanation:
        resource = readable_resource_type(finding.identity.resource_type)
        if finding.drift_type is DriftType.MISSING:
            return FindingExplanation(
                f"The expected {resource} is absent from the live AWS inventory.",
                "Dependent workloads may not receive the infrastructure Terraform expects.",
            )
        if finding.drift_type is DriftType.UNMANAGED:
            return FindingExplanation(
                f"A live {resource} is not represented in the Terraform inventory.",
                "Its ownership and configuration should be verified before it becomes operational debt.",
            )
        changed = ", ".join(sorted(finding.changes)) or "configuration"
        return FindingExplanation(
            f"The {resource} differs from Terraform in: {changed}.",
            "Review the difference to confirm that the deployed configuration remains intended.",
        )


class SafeReconciliationRule:
    def evaluate(self, finding: Finding) -> RemediationPlan:
        resource = readable_resource_type(finding.identity.resource_type)
        return RemediationPlan(
            f"Reconcile the {resource} through the approved infrastructure change process.",
            (
                "If Terraform is the intended state: review terraform plan, obtain approval, then use an approved Terraform apply to restore live AWS.",
                "If the AWS change is intended: update Terraform configuration to match it, review terraform plan, and apply through the approved process.",
                "Do not manually edit Terraform state or apply remediation automatically.",
            ),
        )


def assess_impacts(finding: Finding, rules: tuple[ImpactRule, ...] | None = None) -> ImpactAssessment:
    for rule in rules or default_impact_rules():
        decision = rule.evaluate(finding)
        if decision:
            return decision
    raise ValueError("Impact rules must include a fallback.")


def explain_finding(finding: Finding, rules: tuple[ExplanationRule, ...] | None = None) -> FindingExplanation:
    for rule in rules or default_explanation_rules():
        decision = rule.evaluate(finding)
        if decision:
            return decision
    raise ValueError("Explanation rules must include a fallback.")


def remediation_plan(finding: Finding, rules: tuple[RemediationRule, ...] | None = None) -> RemediationPlan:
    for rule in rules or default_remediation_rules():
        decision = rule.evaluate(finding)
        if decision:
            return decision
    raise ValueError("Remediation rules must include a fallback.")


def default_impact_rules() -> tuple[ImpactRule, ...]:
    return (PublicIngressImpactRule(), PublicRdsImpactRule(), TagOnlyImpactRule(), UnassessedImpactRule())


def default_explanation_rules() -> tuple[ExplanationRule, ...]:
    return (PublicIngressExplanationRule(), TagOnlyExplanationRule(), GenericExplanationRule())


def default_remediation_rules() -> tuple[RemediationRule, ...]:
    return (SafeReconciliationRule(),)


def readable_resource_type(resource_type: str) -> str:
    labels = {
        "security_group": "AWS Security Group",
        "s3_bucket": "AWS S3 Bucket",
        "instance": "AWS EC2 Instance",
        "vpc": "AWS VPC",
        "subnet": "AWS Subnet",
        "internet_gateway": "AWS Internet Gateway",
        "route_table": "AWS Route Table",
        "network_acl": "AWS Network ACL",
        "iam_role": "AWS IAM Role",
        "iam_instance_profile": "AWS IAM Instance Profile",
        "route53_hosted_zone": "AWS Route 53 Hosted Zone",
        "route53_record": "AWS Route 53 Record",
        "nat_gateway": "AWS NAT Gateway",
        "application_load_balancer": "AWS Application Load Balancer",
        "target_group": "AWS Load Balancer Target Group",
        "load_balancer_listener": "AWS Load Balancer Listener",
        "load_balancer_listener_rule": "AWS Load Balancer Listener Rule",
        "rds_db_instance": "AWS RDS DB Instance",
    }
    return labels.get(resource_type, f"AWS {resource_type.replace('_', ' ').title()}")
