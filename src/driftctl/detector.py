"""Pure comparison logic for normalized resource snapshots."""

from __future__ import annotations

from typing import Any, Iterable

from driftctl.models import DriftType, Finding, ResourceSnapshot


def detect_drift(expected: Iterable[ResourceSnapshot], live: Iterable[ResourceSnapshot]) -> list[Finding]:
    expected_by_key = {snapshot.identity.key: snapshot for snapshot in expected}
    live_by_key = {snapshot.identity.key: snapshot for snapshot in live}
    findings: list[Finding] = []

    for key in sorted(expected_by_key.keys() - live_by_key.keys()):
        snapshot = expected_by_key[key]
        findings.append(Finding(DriftType.MISSING, snapshot.identity, snapshot.category, expected=snapshot))
    for key in sorted(live_by_key.keys() - expected_by_key.keys()):
        snapshot = live_by_key[key]
        if snapshot.provider_managed:
            continue
        findings.append(Finding(DriftType.UNMANAGED, snapshot.identity, snapshot.category, live=snapshot))
    for key in sorted(expected_by_key.keys() & live_by_key.keys()):
        changes = diff_attributes(expected_by_key[key].attributes, live_by_key[key].attributes)
        if changes:
            findings.append(Finding(
                DriftType.MODIFIED,
                expected_by_key[key].identity,
                expected_by_key[key].category,
                expected=expected_by_key[key],
                live=live_by_key[key],
                changes=changes,
            ))
    return findings


def diff_attributes(expected: dict[str, Any], live: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return top-level normalized attribute differences with stable list ordering."""
    changes: dict[str, dict[str, Any]] = {}
    for key in sorted(expected.keys() | live.keys()):
        expected_value = expected.get(key)
        live_value = live.get(key)
        if _canonical(expected_value) != _canonical(live_value):
            changes[key] = {"expected": expected_value, "live": live_value}
    return changes


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple((key, _canonical(item)) for key, item in sorted(value.items()))
    if isinstance(value, list):
        return tuple(sorted((_canonical(item) for item in value), key=repr))
    return value
