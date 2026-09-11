"""Canonical security-group permission representation shared by source adapters."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


def canonicalize_security_group_rules(rules: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge equivalent rule fragments into atomic protocol-and-port permissions."""
    grouped: dict[tuple[Any, Any, Any], dict[str, set[str]]] = defaultdict(
        lambda: {
            "cidr_blocks": set(),
            "ipv6_cidr_blocks": set(),
            "prefix_list_ids": set(),
            "security_group_ids": set(),
        }
    )
    for rule in rules:
        key = (rule.get("from_port"), rule.get("to_port"), rule.get("protocol"))
        normalized = grouped[key]
        for attribute in normalized:
            normalized[attribute].update(rule.get(attribute, []))
    return [
        {
            "from_port": from_port,
            "to_port": to_port,
            "protocol": protocol,
            **{attribute: sorted(values) for attribute, values in sources.items()},
        }
        for (from_port, to_port, protocol), sources in sorted(grouped.items(), key=repr)
    ]
