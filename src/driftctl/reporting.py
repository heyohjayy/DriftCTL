"""Markdown reporting for classified scan results."""

from __future__ import annotations

import json
from collections import defaultdict

from driftctl.models import ResourceCategory, ScanResult, Severity


_SEVERITY_ORDER = (Severity.CRITICAL, Severity.SEVERE, Severity.MODERATE, Severity.MINOR)


def render_markdown(result: ScanResult) -> str:
    lines = ["# Infrastructure Drift Report", "", f"- Scan ID: `{result.scan_id}`", f"- Generated: `{result.timestamp}`", f"- Expected resources: {result.expected_count}", f"- Live resources: {result.live_count}", f"- Findings: {len(result.findings)}", ""]
    if result.diagnostics:
        lines.extend(["## Collection Diagnostics", ""])
        for diagnostic in result.diagnostics:
            address = f" `{diagnostic.resource_address}`" if diagnostic.resource_address else ""
            lines.append(f"- [{diagnostic.source}]{address}: {diagnostic.message}")
        lines.append("")
    if not result.findings:
        return "\n".join(lines + ["No drift detected.", ""])
    grouped = defaultdict(list)
    for finding in result.findings:
        grouped[finding.category].append(finding)
    for category in ResourceCategory:
        if not grouped[category]:
            continue
        lines.extend([f"## {category.value}", ""])
        for severity in _SEVERITY_ORDER:
            matches = [finding for finding in grouped[category] if finding.severity is severity]
            if not matches:
                continue
            lines.extend([f"### {severity.value.title()}", ""])
            for finding in matches:
                lines.append(f"#### `{finding.identity.key}` ({finding.drift_type.value})")
                lines.append(f"- Rule: {finding.severity_reason}")
                if finding.changes:
                    lines.append(f"- Differences: `{json.dumps(finding.changes, sort_keys=True)}`")
                lines.append(f"- Proposed remediation: {finding.remediation.summary}")
                lines.extend(f"  - {action}" for action in finding.remediation.actions)
                lines.append("")
    return "\n".join(lines)
