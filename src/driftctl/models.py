"""Provider-neutral domain models used by every layer after ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ResourceCategory(StrEnum):
    IAM = "IAM"
    NETWORKING = "Networking"
    COMPUTE = "Compute"
    STORAGE = "Storage"
    DATABASE = "Database"
    OTHER = "Other"


class DriftType(StrEnum):
    MISSING = "missing"
    UNMANAGED = "unmanaged"
    MODIFIED = "modified"


class Severity(StrEnum):
    CRITICAL = "critical"
    SEVERE = "severe"
    MODERATE = "moderate"
    MINOR = "minor"


@dataclass(frozen=True)
class ResourceIdentity:
    provider: str
    resource_type: str
    name: str

    @property
    def key(self) -> str:
        return f"{self.provider}:{self.resource_type}:{self.name}"


@dataclass(frozen=True)
class ResourceSnapshot:
    identity: ResourceIdentity
    category: ResourceCategory
    attributes: dict[str, Any]
    source_address: str | None = None


@dataclass(frozen=True)
class RemediationRecommendation:
    summary: str
    actions: tuple[str, ...]


@dataclass(frozen=True)
class CollectionDiagnostic:
    source: str
    message: str
    resource_address: str | None = None


@dataclass
class Finding:
    drift_type: DriftType
    identity: ResourceIdentity
    category: ResourceCategory
    expected: ResourceSnapshot | None = None
    live: ResourceSnapshot | None = None
    changes: dict[str, dict[str, Any]] = field(default_factory=dict)
    severity: Severity | None = None
    severity_reason: str | None = None
    remediation: RemediationRecommendation | None = None


@dataclass(frozen=True)
class ScanResult:
    scan_id: str
    timestamp: str
    expected_count: int
    live_count: int
    findings: tuple[Finding, ...]
    diagnostics: tuple[CollectionDiagnostic, ...] = ()
