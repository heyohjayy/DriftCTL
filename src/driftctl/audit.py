"""Tamper-evident JSONL audit writer for read-only scan evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from driftctl.models import ScanResult


_AUDIT_SCHEMA = "driftctl.audit.v1"


class AuditIntegrityError(RuntimeError):
    """An existing audit log cannot be verified safely."""


def write_audit_log(path: Path, result: ScanResult) -> int:
    """Verify the existing chain, then append hash-chained scan events."""
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_hash, legacy_bytes = _verify_existing_log(path)
    events = _events_for(result)
    with path.open("ab") as audit_file:
        if legacy_bytes is not None:
            anchor = {
                "event_type": "audit_chain_anchor",
                "legacy_event_count": _json_line_count(legacy_bytes),
                "legacy_sha256": hashlib.sha256(legacy_bytes).hexdigest(),
            }
            previous_hash = _write_chained_event(audit_file, anchor, previous_hash)
        for event in events:
            previous_hash = _write_chained_event(audit_file, event, previous_hash)
    return len(events) + (1 if legacy_bytes is not None else 0)


def verify_audit_log(path: Path) -> None:
    """Raise AuditIntegrityError unless the chained portion verifies."""
    _verify_existing_log(path)


def _events_for(result: ScanResult) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [{
        "event_type": "scan", "scan_id": result.scan_id, "timestamp": result.timestamp,
        "expected_count": result.expected_count, "live_count": result.live_count,
        "finding_count": len(result.findings), "diagnostic_count": len(result.diagnostics),
    }]
    for diagnostic in result.diagnostics:
        events.append({"event_type": "collection_diagnostic", "scan_id": result.scan_id, "diagnostic": asdict(diagnostic)})
    for finding in result.findings:
        events.append({"event_type": "finding", "scan_id": result.scan_id, "finding": asdict(finding)})
        events.append({"event_type": "severity_decision", "scan_id": result.scan_id, "resource": finding.identity.key, "severity": finding.severity, "reason": finding.severity_reason})
        events.append({"event_type": "remediation", "scan_id": result.scan_id, "resource": finding.identity.key, "recommendation": asdict(finding.remediation)})
    return events


def _verify_existing_log(path: Path) -> tuple[str | None, bytes | None]:
    if not path.exists() or not path.stat().st_size:
        return None, None
    raw_lines = path.read_bytes().splitlines(keepends=True)
    events = [_parse_line(line, path) for line in raw_lines if line.strip()]
    first_chained = next((index for index, event in enumerate(events) if event.get("audit_schema") == _AUDIT_SCHEMA), len(events))
    legacy_lines = raw_lines[:first_chained]
    if first_chained == len(events):
        return None, b"".join(legacy_lines)

    previous_hash: str | None = None
    for index, event in enumerate(events[first_chained:], start=first_chained):
        _validate_chained_event(event, previous_hash, path, index + 1)
        if index == first_chained and legacy_lines:
            if event.get("event_type") != "audit_chain_anchor":
                raise AuditIntegrityError(f"Legacy audit history in {path} is missing its chain anchor.")
            legacy_bytes = b"".join(legacy_lines)
            if event.get("legacy_sha256") != hashlib.sha256(legacy_bytes).hexdigest():
                raise AuditIntegrityError(f"Legacy audit history was changed in {path}.")
            if event.get("legacy_event_count") != _json_line_count(legacy_bytes):
                raise AuditIntegrityError(f"Legacy audit event count was changed in {path}.")
        previous_hash = event["event_hash"]
    return previous_hash, None


def _parse_line(line: bytes, path: Path) -> dict[str, Any]:
    try:
        event = json.loads(line)
    except json.JSONDecodeError as error:
        raise AuditIntegrityError(f"Audit log contains invalid JSON: {path}.") from error
    if not isinstance(event, dict):
        raise AuditIntegrityError(f"Audit log contains a non-object event: {path}.")
    return event


def _validate_chained_event(event: dict[str, Any], previous_hash: str | None, path: Path, line_number: int) -> None:
    if event.get("previous_hash") != previous_hash:
        raise AuditIntegrityError(f"Audit chain link mismatch at {path}:{line_number}.")
    if event.get("event_hash") != _event_hash(event):
        raise AuditIntegrityError(f"Audit event hash mismatch at {path}:{line_number}.")


def _write_chained_event(audit_file: Any, event: dict[str, Any], previous_hash: str | None) -> str:
    chained = dict(event, audit_schema=_AUDIT_SCHEMA, previous_hash=previous_hash)
    event_hash = _event_hash(chained)
    chained["event_hash"] = event_hash
    audit_file.write(_canonical_json(chained).encode("utf-8") + b"\n")
    return event_hash


def _event_hash(event: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in event.items() if key != "event_hash"}
    return hashlib.sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _json_line_count(value: bytes) -> int:
    return len([line for line in value.splitlines() if line.strip()])
