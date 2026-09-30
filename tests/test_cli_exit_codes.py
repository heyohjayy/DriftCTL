from driftctl.cli import _scan_exit_code
from driftctl.models import DriftType, Finding, ResourceCategory, ResourceIdentity, Severity


def _finding(severity: Severity) -> Finding:
    finding = Finding(DriftType.MODIFIED, ResourceIdentity("aws", "vpc", "demo"), ResourceCategory.NETWORKING)
    finding.severity = severity
    return finding


def test_clean_scan_returns_success() -> None:
    assert _scan_exit_code([], None) == 0


def test_any_drift_returns_drift_exit_code_by_default() -> None:
    assert _scan_exit_code([_finding(Severity.MINOR)], None) == 2


def test_fail_on_threshold_only_fails_at_or_above_selected_severity() -> None:
    assert _scan_exit_code([_finding(Severity.MODERATE)], Severity.SEVERE) == 0
    assert _scan_exit_code([_finding(Severity.SEVERE)], Severity.SEVERE) == 2
