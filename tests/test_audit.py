from __future__ import annotations

import json
from pathlib import Path

import pytest

from driftctl.audit import AuditIntegrityError, verify_audit_log, write_audit_log
from driftctl.models import ScanResult


def _result(scan_id: str = "scan-1") -> ScanResult:
    return ScanResult(scan_id, "2026-09-30T12:00:00+00:00", 1, 1, ())


def test_new_audit_log_is_hash_chained_and_can_be_appended(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"

    assert write_audit_log(path, _result()) == 1
    assert write_audit_log(path, _result("scan-2")) == 1
    verify_audit_log(path)

    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert events[0]["previous_hash"] is None
    assert events[1]["previous_hash"] == events[0]["event_hash"]
    assert all(event["audit_schema"] == "driftctl.audit.v1" for event in events)


def test_changed_chained_event_blocks_new_evidence(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_audit_log(path, _result())
    path.write_text(path.read_text(encoding="utf-8").replace('"scan-1"', '"scan-x"'), encoding="utf-8")

    with pytest.raises(AuditIntegrityError, match="hash mismatch"):
        write_audit_log(path, _result("scan-2"))


def test_legacy_history_is_preserved_and_anchored(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    legacy = '{"event_type":"scan","scan_id":"legacy"}\n'
    path.write_text(legacy, encoding="utf-8")

    assert write_audit_log(path, _result()) == 2
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == legacy.strip()
    assert json.loads(lines[1])["event_type"] == "audit_chain_anchor"
    verify_audit_log(path)


def test_legacy_history_change_is_detected_after_anchoring(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text('{"event_type":"scan","scan_id":"legacy"}\n', encoding="utf-8")
    write_audit_log(path, _result())
    path.write_text(path.read_text(encoding="utf-8").replace('"legacy"', '"altered"'), encoding="utf-8")

    with pytest.raises(AuditIntegrityError, match="Legacy audit history was changed"):
        verify_audit_log(path)
