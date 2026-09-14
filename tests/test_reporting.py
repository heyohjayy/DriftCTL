from io import StringIO

from rich.console import Console

from driftctl.models import DriftType, Finding, ResourceCategory, ResourceIdentity, ResourceSnapshot, ScanResult, Severity
from driftctl.presentation import ImpactLevel, assess_impacts, explain_finding, remediation_plan
from driftctl.reporting import render_markdown, render_terminal
from driftctl.severity_rules import classify_finding, default_rules


def _snapshot(resource_type: str, category: ResourceCategory, attributes: dict) -> ResourceSnapshot:
    return ResourceSnapshot(ResourceIdentity("aws", resource_type, "demo"), category, attributes)


def _result(finding: Finding) -> ScanResult:
    return ScanResult("scan-report", "2026-09-14T00:00:00+00:00", 1, 1, (finding,), tag_scope="Project=Test")


def test_public_ssh_report_guidance_is_critical_with_assessed_impacts() -> None:
    live = _snapshot("security_group", ResourceCategory.NETWORKING, {"ingress": [{"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}]})
    finding = Finding(DriftType.MODIFIED, live.identity, live.category, live=live, changes={"ingress": {"expected": [], "live": live.attributes["ingress"]}})

    classify_finding(finding, default_rules())
    impact = assess_impacts(finding)
    explanation = explain_finding(finding)
    plan = remediation_plan(finding)

    assert finding.severity is Severity.CRITICAL
    assert (impact.security, impact.cost, impact.availability) == (
        ImpactLevel.HIGH,
        ImpactLevel.NONE,
        ImpactLevel.LOW,
    )
    assert "public SSH" in explanation.change
    assert "obtain approval" in " ".join(plan.actions)


def test_tag_only_drift_has_low_no_none_impacts_and_safe_guidance() -> None:
    live = _snapshot("vpc", ResourceCategory.NETWORKING, {"tags": {"Owner": "platform"}})
    finding = Finding(DriftType.MODIFIED, live.identity, live.category, live=live, changes={"tags": {"expected": {"Owner": "infra"}, "live": live.attributes["tags"]}})

    classify_finding(finding, default_rules())

    impact = assess_impacts(finding)
    assert (impact.security, impact.cost, impact.availability) == (
        ImpactLevel.LOW,
        ImpactLevel.NONE,
        ImpactLevel.NONE,
    )
    assert "tags differ" in explain_finding(finding).change
    assert "Do not manually edit Terraform state" in " ".join(remediation_plan(finding).actions)


def test_unassessed_drift_reports_not_assessed_impacts() -> None:
    live = _snapshot("future_resource", ResourceCategory.OTHER, {"setting": "live"})
    finding = Finding(DriftType.MODIFIED, live.identity, live.category, live=live, changes={"setting": {"expected": "expected", "live": "live"}})

    impact = assess_impacts(finding)
    assert (impact.security, impact.cost, impact.availability) == (
        ImpactLevel.NOT_ASSESSED,
        ImpactLevel.NOT_ASSESSED,
        ImpactLevel.NOT_ASSESSED,
    )


def test_terminal_and_markdown_include_operational_finding_details() -> None:
    live = _snapshot("security_group", ResourceCategory.NETWORKING, {"ingress": [{"from_port": 22, "to_port": 22, "protocol": "tcp", "cidr_blocks": ["0.0.0.0/0"]}]})
    finding = Finding(DriftType.MODIFIED, live.identity, live.category, live=live, changes={"ingress": {"expected": [], "live": live.attributes["ingress"]}})
    classify_finding(finding, default_rules())
    result = _result(finding)
    stream = StringIO()

    render_terminal(result, Console(file=stream, force_terminal=False, width=160))
    terminal = stream.getvalue()
    markdown = render_markdown(result)

    for rendered in (terminal, markdown):
        assert "DRIFT-0001" in rendered
        assert "0.0.0.0/0" in rendered
        assert "Requires approval" in rendered
        assert "DriftCTL reports drift only. It does not modify AWS or run Terraform." in rendered


def test_supported_non_security_drift_uses_understandable_fallback() -> None:
    live = _snapshot("subnet", ResourceCategory.NETWORKING, {"cidr_block": "10.0.2.0/24"})
    finding = Finding(DriftType.MODIFIED, live.identity, live.category, live=live, changes={"cidr_block": {"expected": "10.0.1.0/24", "live": "10.0.2.0/24"}})

    explanation = explain_finding(finding)
    plan = remediation_plan(finding)

    assert "AWS Subnet differs from Terraform" in explanation.change
    assert "Terraform is the intended state" in " ".join(plan.actions)
