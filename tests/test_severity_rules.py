from driftctl.models import DriftType, Finding, ResourceCategory, ResourceIdentity, ResourceSnapshot, Severity
from driftctl.severity_rules import classify_finding, default_rules


def make_snapshot(category: ResourceCategory, attributes: dict) -> ResourceSnapshot:
    return ResourceSnapshot(ResourceIdentity("aws", "resource", "demo"), category, attributes)


def test_public_ssh_is_critical() -> None:
    live = make_snapshot(ResourceCategory.NETWORKING, {"ingress": [{"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}]})
    finding = Finding(DriftType.MODIFIED, live.identity, live.category, live=live, changes={"ingress": {"expected": [], "live": live.attributes["ingress"]}})
    classify_finding(finding, default_rules())
    assert finding.severity is Severity.CRITICAL
    assert "DangerousSecurityGroupIngressRule" in finding.severity_reason


def test_s3_protection_regression_is_severe() -> None:
    live = make_snapshot(ResourceCategory.STORAGE, {})
    finding = Finding(DriftType.MODIFIED, live.identity, live.category, live=live, changes={"public_access_block": {"expected": {"block_public_policy": True}, "live": {"block_public_policy": False}}, "encryption": {"expected": {"sse_algorithm": "AES256"}, "live": {}}})
    classify_finding(finding, default_rules())
    assert finding.severity is Severity.SEVERE
    assert "S3ProtectionRegressionRule" in finding.severity_reason
