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


class UnexpectedPublicRouteRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.category is not ResourceCategory.NETWORKING or finding.identity.resource_type != "route_table":
            return None
        if finding.drift_type is DriftType.MODIFIED and "routes" not in finding.changes:
            return None
        snapshot = finding.live or finding.expected
        if snapshot and any(route.get("target_type") == "internet_gateway" and (route.get("destination_ipv4") == "0.0.0.0/0" or route.get("destination_ipv6") == "::/0") for route in snapshot.attributes.get("routes", [])):
            return SeverityDecision(Severity.SEVERE, "UnexpectedPublicRouteRule: a route table exposes a default IPv4 route through an internet gateway.", RemediationRecommendation("Confirm the public route is intentional before retaining it.", ("Review attached subnet associations.", "Restrict or remove the route in Terraform after approval.")))
        return None


class PermissiveNetworkAclRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.category is not ResourceCategory.NETWORKING or finding.identity.resource_type != "network_acl":
            return None
        if finding.drift_type is DriftType.MODIFIED and "entries" not in finding.changes:
            return None
        snapshot = finding.live or finding.expected
        if snapshot and any(not entry.get("egress") and entry.get("action") == "allow" and (entry.get("cidr_block") == "0.0.0.0/0" or entry.get("ipv6_cidr_block") == "::/0") and entry.get("protocol") == "-1" for entry in snapshot.attributes.get("entries", [])):
            return SeverityDecision(Severity.SEVERE, "PermissiveNetworkAclRule: inbound network ACL permits all traffic from 0.0.0.0/0.", RemediationRecommendation("Restrict the ACL entry to approved sources and protocols.", ("Confirm the entry is not a temporary exception.", "Reconcile the ACL through a reviewed Terraform change.")))
        return None


class IamAdministratorAccessRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.category is not ResourceCategory.IAM or finding.identity.resource_type != "iam_role":
            return None
        if finding.drift_type is DriftType.MODIFIED and not {"managed_policy_arns", "inline_policies"}.intersection(finding.changes):
            return None
        snapshot = finding.live or finding.expected
        if snapshot and (_has_administrator_access(snapshot.attributes.get("managed_policy_arns", [])) or _has_broad_inline_policy(snapshot.attributes.get("inline_policies", []))):
            return SeverityDecision(Severity.CRITICAL, "IamAdministratorAccessRule: role has AdministratorAccess or an equivalent broad inline policy.", RemediationRecommendation("Remove broad administrative access unless it is explicitly approved.", ("Validate the role's business purpose and owner.", "Replace broad permissions with least-privilege Terraform policy statements.")))
        return None


class RiskyTrustPolicyRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.category is not ResourceCategory.IAM or finding.identity.resource_type != "iam_role":
            return None
        if finding.drift_type is DriftType.MODIFIED and "trust_policy" not in finding.changes:
            return None
        snapshot = finding.live or finding.expected
        if snapshot and _has_unrestricted_trust(snapshot.attributes.get("trust_policy", {})):
            return SeverityDecision(Severity.SEVERE, "RiskyTrustPolicyRule: role trust policy permits unrestricted principal assumption.", RemediationRecommendation("Constrain the trust policy principal and conditions.", ("Identify intended assuming principals.", "Update the Terraform trust policy and review the resulting plan.")))
        return None


class DnsRecordChangeRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.drift_type is DriftType.MODIFIED and finding.identity.resource_type == "route53_record":
            return SeverityDecision(Severity.MODERATE, "DnsRecordChangeRule: Route 53 record values differ from Terraform state.", RemediationRecommendation("Validate the DNS target before reconciliation.", ("Confirm the intended record owner and destination.", "Reconcile the record through a reviewed Terraform change.")))
        return None


class RdsPublicAccessRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.identity.resource_type != "rds_db_instance" or finding.drift_type not in {DriftType.MODIFIED, DriftType.UNMANAGED}:
            return None
        if finding.live and finding.live.attributes.get("publicly_accessible"):
            return SeverityDecision(
                Severity.SEVERE,
                "RdsPublicAccessRule: an RDS DB instance is publicly accessible.",
                RemediationRecommendation(
                    "Review and remove public database exposure through an approved Terraform change.",
                    ("Validate whether public reachability is explicitly required.", "Prefer private subnets and restricted security groups.", "Review terraform plan and obtain approval before apply."),
                ),
            )
        return None


class RdsProtectionRegressionRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.identity.resource_type != "rds_db_instance" or finding.drift_type is not DriftType.MODIFIED:
            return None
        encryption = finding.changes.get("storage_encrypted")
        deletion = finding.changes.get("deletion_protection")
        encryption_weakened = bool(encryption and encryption.get("expected") and not encryption.get("live"))
        deletion_weakened = bool(deletion and deletion.get("expected") and not deletion.get("live"))
        if encryption_weakened or deletion_weakened:
            return SeverityDecision(
                Severity.SEVERE,
                "RdsProtectionRegressionRule: expected encryption or deletion protection was weakened.",
                RemediationRecommendation("Restore the approved RDS protection settings after review.", ("Confirm whether the change was authorized.", "Review terraform plan and obtain approval before apply.")),
            )
        return None


class EcsPublicIpRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.identity.resource_type != "ecs_service" or finding.drift_type not in {DriftType.MODIFIED, DriftType.UNMANAGED}:
            return None
        network = finding.live.attributes.get("network_configuration", {}) if finding.live else {}
        if network.get("assign_public_ip"):
            return SeverityDecision(
                Severity.MODERATE,
                "EcsPublicIpRule: ECS tasks are configured to receive public IP addresses.",
                RemediationRecommendation(
                    "Validate that direct task internet reachability is required.",
                    ("Review subnet routes and security groups.", "Prefer private task networking when the service design permits it.", "Reconcile through a reviewed Terraform plan after approval."),
                ),
            )
        return None


class LogRetentionChangeRule:
    def evaluate(self, finding: Finding) -> SeverityDecision | None:
        if finding.identity.resource_type != "cloudwatch_log_group" or finding.drift_type is not DriftType.MODIFIED:
            return None
        change = finding.changes.get("retention_in_days")
        if not change:
            return None
        expected, live = change.get("expected"), change.get("live")
        weakened = expected is not None and (live is None or isinstance(live, int) and live < expected)
        severity = Severity.MODERATE if weakened else Severity.MINOR
        return SeverityDecision(
            severity,
            "LogRetentionChangeRule: CloudWatch log retention differs from the approved Terraform setting.",
            RemediationRecommendation(
                "Confirm the required operational and compliance retention period.",
                ("Estimate storage and investigation-history impact.", "Reconcile retention through a reviewed Terraform plan after approval."),
            ),
        )


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
    return [DangerousSecurityGroupIngressRule(), UnexpectedPublicRouteRule(), PermissiveNetworkAclRule(), IamAdministratorAccessRule(), RiskyTrustPolicyRule(), S3ProtectionRegressionRule(), RdsPublicAccessRule(), RdsProtectionRegressionRule(), EcsPublicIpRule(), LogRetentionChangeRule(), DnsRecordChangeRule(), MissingResourceRule(), UnmanagedRiskRule(), TagOnlyRule(), DefaultModifiedRule(), DefaultUnmanagedRule()]


def _has_administrator_access(policy_arns: list[str]) -> bool:
    return any(arn.endswith(":policy/AdministratorAccess") for arn in policy_arns)


def _has_broad_inline_policy(policies: list[dict]) -> bool:
    for policy in policies:
        document = policy.get("document", {})
        for statement in document.get("Statement", []) if isinstance(document, dict) else []:
            actions = statement.get("Action", []); resources = statement.get("Resource", [])
            if statement.get("Effect") == "Allow" and (actions == "*" or "*" in actions) and (resources == "*" or "*" in resources): return True
    return False


def _has_unrestricted_trust(policy: object) -> bool:
    if not isinstance(policy, dict): return False
    for statement in policy.get("Statement", []):
        actions = statement.get("Action", [])
        principal = statement.get("Principal")
        wildcard_principal = principal == "*" or isinstance(principal, dict) and any(value == "*" or isinstance(value, list) and "*" in value for value in principal.values())
        if statement.get("Effect") == "Allow" and (actions == "sts:AssumeRole" or "sts:AssumeRole" in actions) and wildcard_principal: return True
    return False
