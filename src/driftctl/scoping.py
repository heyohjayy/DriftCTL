"""Environment-scope parsing and provider-neutral resource filtering."""

from __future__ import annotations

from collections.abc import Iterable

from driftctl.models import ResourceSnapshot


def parse_tag_scope(values: list[str]) -> dict[str, str]:
    """Parse repeatable KEY=VALUE CLI options into an AND-matched tag scope."""
    scope: dict[str, str] = {}
    for value in values:
        key, separator, tag_value = value.partition("=")
        if not separator or not key or not tag_value:
            raise ValueError(f"Invalid --tag value {value!r}; use KEY=VALUE.")
        if key in scope and scope[key] != tag_value:
            raise ValueError(f"Conflicting --tag values provided for {key!r}.")
        scope[key] = tag_value
    return scope


def filter_snapshots_by_tag_scope(
    snapshots: Iterable[ResourceSnapshot],
    tag_scope: dict[str, str],
) -> list[ResourceSnapshot]:
    """Return snapshots matching every scope tag, or all snapshots when unscoped."""
    if not tag_scope:
        return list(snapshots)
    return [
        snapshot
        for snapshot in snapshots
        if all(snapshot.attributes.get("tags", {}).get(key) == value for key, value in tag_scope.items())
    ]


def format_tag_scope(tag_scope: dict[str, str]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(tag_scope.items()))
