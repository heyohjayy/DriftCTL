"""Composable severity policies applied after provider-neutral drift detection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from driftctl.models import DriftType, Finding, RemediationRecommendation, ResourceCategory, Severity


@dataclass(frozen=True)
class SeverityDecision:
    severity: Severity
    reason: str
    remediation: RemediationRecommendation


class SeverityRule(Protocol):
    def evaluate(self, finding: Finding) -> SeverityDecision | None: ...


def classify_finding(finding: Finding, rules: list[SeverityRule]) -> Finding:
    for rule in rules:
        decision = rule.evaluate(finding)
        if decision:
            finding.severity = decision.severity
            finding.severity_reason = decision.reason
            finding.remediation = decision.remediation
            return finding
    raise ValueError(f"No severity rule matched {finding.identity.key}")


class DangerousSecurityGroupIngressRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        snapshot = finding.live or finding.expected
        if snapshot and snapshot.category is ResourceCategory.NETWORKING and has_dangerous_ingress(snapshot.attributes.get("ingress", [])):
            return SeverityDecision(
                Severity.CRITICAL,
                "DangerousSecurityGroupIngressRule: SSH, RDP, or all ports are exposed to 0.0.0.0/0.",
                RemediationRecommendation(
                    "Remove the public administrative ingress and restore least-privilege network access.",
                    ("Review the source and approval for the ingress rule.", "Constrain the CIDR and port in Terraform.", "Run terraform plan and obtain approval before apply."),
                ),
            )
        return None


class S3ProtectionRegressionRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.drift_type is not DriftType.MODIFIED or finding.category is not ResourceCategory.STORAGE:
            return None
        public_access = finding.changes.get("public_access_block")
        encryption = finding.changes.get("encryption")
        public_weakened = public_access and _public_access_weakened(public_access["expected"], public_access["live"])
        encryption_weakened = encryption and bool(encryption["expected"]) and not bool(encryption["live"])
        if public_weakened or encryption_weakened:
            return SeverityDecision(
                Severity.SEVERE,
                "S3ProtectionRegressionRule: expected S3 public-access protection or default encryption was weakened.",
                RemediationRecommendation(
                    "Restore the approved S3 protection controls through Terraform.",
                    ("Confirm whether the change was an approved emergency action.", "Restore public-access-block and encryption settings in Terraform.", "Review a Terraform plan before any apply."),
                ),
            )
        return None


class MissingResourceRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.drift_type is DriftType.MISSING:
            return SeverityDecision(
                Severity.SEVERE,
                "MissingResourceRule: a Terraform-managed resource is absent from the live inventory.",
                RemediationRecommendation(
                    "Investigate deletion before recreating the expected resource.",
                    ("Confirm the resource is absent in the authoritative AWS account and region.", "Review deletion events and dependent services.", "Use a reviewed Terraform plan to restore it if appropriate."),
                ),
            )
        return None


class UnmanagedRiskRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.drift_type is not DriftType.UNMANAGED or not finding.live:
            return None
        attrs = finding.live.attributes
        risky_network = finding.category is ResourceCategory.NETWORKING and has_dangerous_ingress(attrs.get("ingress", []))
        risky_storage = finding.category is ResourceCategory.STORAGE and _public_access_weakened(
            {"block_public_acls": True, "ignore_public_acls": True, "block_public_policy": True, "restrict_public_buckets": True},
            attrs.get("public_access_block", {}),
        )
        risky_compute = finding.category is ResourceCategory.COMPUTE and bool(attrs.get("associate_public_ip_address"))
        if risky_network or risky_storage or risky_compute:
            return SeverityDecision(
                Severity.SEVERE,
                "UnmanagedRiskRule: an unmanaged resource has public exposure or unsafe security configuration.",
                RemediationRecommendation(
                    "Contain the exposure, then either import the resource or remove it through an approved change.",
                    ("Verify the resource owner and business purpose.", "Restrict exposure immediately under incident/change-control policy.", "Import to Terraform or remove it after approval."),
                ),
            )
        return None


class TagOnlyRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.drift_type is DriftType.MODIFIED and set(finding.changes) <= {"tags"}:
            return SeverityDecision(
                Severity.MINOR,
                "TagOnlyRule: only metadata tags differ from the expected inventory.",
                RemediationRecommendation(
                    "Reconcile tags after confirming the intended ownership metadata.",
                    ("Confirm authoritative tags with the resource owner.", "Update Terraform or the live tags through an approved change."),
                ),
            )
        return None


class DefaultModifiedRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.drift_type is DriftType.MODIFIED:
            return SeverityDecision(Severity.MODERATE, "DefaultModifiedRule: meaningful configuration differs from Terraform state.", _generic_remediation())
        return None


class DefaultUnmanagedRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.drift_type is DriftType.UNMANAGED:
            return SeverityDecision(Severity.MODERATE, "DefaultUnmanagedRule: resource exists outside the expected Terraform inventory.", _generic_remediation())
        return None


def has_dangerous_ingress(rules: list[dict[str, object]]) -> bool:
    for rule in rules:
        if "0.0.0.0/0" not in rule.get("cidr_blocks", []):
            continue
        protocol = str(rule.get("protocol"))
        from_port, to_port = rule.get("from_port"), rule.get("to_port")
        if protocol == "-1" or (isinstance(from_port, int) and isinstance(to_port, int) and from_port <= 0 and to_port >= 65535):
            return True
        if isinstance(from_port, int) and isinstance(to_port, int) and any(from_port <= port <= to_port for port in (22, 3389)):
            return True
    return False


def _public_access_weakened(expected: object, live: object) -> bool:
    if not isinstance(expected, dict) or not isinstance(live, dict):
        return False
    return any(expected.get(key) is True and live.get(key) is not True for key in expected)


def _generic_remediation() -> RemediationRecommendation:
    return RemediationRecommendation("Reconcile the approved state without applying automatically.", ("Confirm whether the difference is intended.", "Update Terraform or import the resource as appropriate.", "Review a Terraform plan before any apply."))


def default_rules() -> list[SeverityRule]:
    return [DangerousSecurityGroupIngressRule(), S3ProtectionRegressionRule(), MissingResourceRule(), UnmanagedRiskRule(), TagOnlyRule(), DefaultModifiedRule(), DefaultUnmanagedRule()]
