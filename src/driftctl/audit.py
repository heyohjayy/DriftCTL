"""Append-only JSONL audit event writer."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from driftctl.models import ScanResult


def write_audit_log(path: Path, result: ScanResult) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    events: list[dict[str, Any]] = [{"event_type": "scan", "scan_id": result.scan_id, "timestamp": result.timestamp, "expected_count": result.expected_count, "live_count": result.live_count, "finding_count": len(result.findings), "diagnostic_count": len(result.diagnostics)}]
    for diagnostic in result.diagnostics:
        events.append({"event_type": "collection_diagnostic", "scan_id": result.scan_id, "diagnostic": asdict(diagnostic)})
    for finding in result.findings:
        finding_data = asdict(finding)
        events.append({"event_type": "finding", "scan_id": result.scan_id, "finding": finding_data})
        events.append({"event_type": "severity_decision", "scan_id": result.scan_id, "resource": finding.identity.key, "severity": finding.severity, "reason": finding.severity_reason})
        events.append({"event_type": "remediation", "scan_id": result.scan_id, "resource": finding.identity.key, "recommendation": asdict(finding.remediation)})
    with path.open("a", encoding="utf-8") as audit_file:
        for event in events:
            audit_file.write(json.dumps(event, default=str, sort_keys=True) + "\n")
    return len(events)
