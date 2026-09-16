"""Shared canonicalization for Terraform and boto3 ECS shapes."""

from __future__ import annotations

import json
from typing import Any


def task_definition_ref(value: Any) -> str | None:
    """Return the stable family:revision portion of an ECS task definition reference."""
    if not value:
        return None
    return str(value).rsplit("/", 1)[-1]


def container_definitions(value: Any) -> list[dict[str, Any]]:
    """Parse Terraform JSON and normalize unordered ECS container collections."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    return sorted((_container(item) for item in value), key=lambda item: item["name"] or "")


def capacity_provider_strategy(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    return sorted(
        (
            {
                "capacity_provider": item.get("capacity_provider", item.get("capacityProvider")),
                "weight": item.get("weight", 0),
                "base": item.get("base", 0),
            }
            for item in values
        ),
        key=lambda item: (item["capacity_provider"] or "", item["weight"], item["base"]),
    )


def assign_public_ip(value: Any) -> bool:
    if isinstance(value, str):
        return value.upper() == "ENABLED"
    return bool(value)


def cluster_settings(values: Any) -> dict[str, str]:
    settings = {
        item.get("name"): item.get("value")
        for item in values or []
        if isinstance(item, dict) and item.get("name")
    }
    return {"containerInsights": settings.get("containerInsights", "disabled")}


def runtime_platform(value: Any) -> dict[str, Any]:
    item = _first(value)
    return {
        "cpu_architecture": item.get("cpu_architecture", item.get("cpuArchitecture")),
        "operating_system_family": item.get("operating_system_family", item.get("operatingSystemFamily")),
    }


def _container(item: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "name": item.get("name"),
        "image": item.get("image"),
        "cpu": item.get("cpu", 0),
        "memory": item.get("memory"),
        "memoryReservation": item.get("memoryReservation"),
        "essential": item.get("essential", True),
        "portMappings": sorted((_port(port) for port in item.get("portMappings", [])), key=repr),
        "environment": sorted((_named_value(entry, "value") for entry in item.get("environment", [])), key=repr),
        "secrets": sorted((_named_value(entry, "valueFrom") for entry in item.get("secrets", [])), key=repr),
        "mountPoints": sorted((_mount(mount) for mount in item.get("mountPoints", [])), key=repr),
        "readonlyRootFilesystem": item.get("readonlyRootFilesystem", False),
    }
    for key in ("command", "entryPoint", "dependsOn", "healthCheck", "linuxParameters", "firelensConfiguration"):
        if key in item:
            normalized[key] = _stable(item[key])
    if item.get("logConfiguration"):
        log = item["logConfiguration"]
        normalized["logConfiguration"] = {
            "logDriver": log.get("logDriver"),
            "options": dict(sorted((log.get("options") or {}).items())),
            "secretOptions": sorted((_named_value(entry, "valueFrom") for entry in log.get("secretOptions", [])), key=repr),
        }
    return normalized


def _port(item: dict[str, Any]) -> dict[str, Any]:
    container_port = item.get("containerPort")
    return {
        "containerPort": container_port,
        "hostPort": item.get("hostPort", container_port),
        "protocol": item.get("protocol", "tcp"),
        "appProtocol": item.get("appProtocol"),
    }


def _named_value(item: dict[str, Any], value_key: str) -> dict[str, Any]:
    return {"name": item.get("name"), value_key: item.get(value_key)}


def _mount(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "sourceVolume": item.get("sourceVolume"),
        "containerPath": item.get("containerPath"),
        "readOnly": item.get("readOnly", False),
    }


def _first(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return value[0] if value else {}
    return value if isinstance(value, dict) else {}


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stable(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value
