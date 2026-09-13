"""Safe, non-secret TOML configuration for DriftCTL scans."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ScanConfigError(ValueError):
    """A scan configuration is malformed, unsafe, or incomplete."""


@dataclass(frozen=True)
class ScanConfig:
    terraform_dir: Path | None = None
    aws_profile: str | None = None
    region: str | None = None
    tags: tuple[str, ...] = ()
    report: Path | None = None
    audit: Path | None = None


_ALLOWED_KEYS = {"terraform_dir", "aws_profile", "region", "tags", "report", "audit"}
_SECRET_MARKERS = ("secret", "access_key", "password", "credential", "token")


def load_scan_config(config_path: Path | None, cwd: Path | None = None) -> ScanConfig | None:
    """Load an explicit config or auto-discover ``driftctl.toml`` in the CWD."""
    candidate = config_path or (cwd or Path.cwd()) / "driftctl.toml"
    if config_path is None and not candidate.exists():
        return None
    if not candidate.is_file():
        raise ScanConfigError(f"Scan config file does not exist: {candidate}")
    try:
        with candidate.open("rb") as config_file:
            payload = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as error:
        raise ScanConfigError(f"Malformed TOML in {candidate}: {error}") from error
    if set(payload) != {"scan"} or not isinstance(payload.get("scan"), dict):
        raise ScanConfigError("Scan config must contain exactly one [scan] section.")
    section = payload["scan"]
    _validate_keys(section)
    return ScanConfig(
        terraform_dir=_path_value(section, "terraform_dir", candidate),
        aws_profile=_string_value(section, "aws_profile"),
        region=_string_value(section, "region"),
        tags=_tag_values(section),
        report=_path_value(section, "report", candidate),
        audit=_path_value(section, "audit", candidate),
    )


def _validate_keys(section: dict[str, Any]) -> None:
    unknown = set(section) - _ALLOWED_KEYS
    secret_keys = [key for key in section if any(marker in key.lower() for marker in _SECRET_MARKERS)]
    if secret_keys:
        raise ScanConfigError(f"Scan config must not contain AWS secrets or credentials: {', '.join(sorted(secret_keys))}.")
    if unknown:
        raise ScanConfigError(f"Unsupported [scan] configuration key(s): {', '.join(sorted(unknown))}.")


def _string_value(section: dict[str, Any], key: str) -> str | None:
    value = section.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ScanConfigError(f"[scan].{key} must be a non-empty string.")
    return value


def _path_value(section: dict[str, Any], key: str, config_path: Path) -> Path | None:
    value = _string_value(section, key)
    if value is None:
        return None
    path = Path(value)
    return path if path.is_absolute() else config_path.parent / path


def _tag_values(section: dict[str, Any]) -> tuple[str, ...]:
    value = section.get("tags", [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ScanConfigError("[scan].tags must be an array of KEY=VALUE strings.")
    return tuple(value)
