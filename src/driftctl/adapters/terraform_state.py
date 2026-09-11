"""Translate terraform show -json-style state into domain snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from driftctl.models import CollectionDiagnostic, ResourceCategory, ResourceIdentity, ResourceSnapshot
from driftctl.adapters.security_group_rules import canonicalize_security_group_rules


_SUPPORTED_RESOURCE_TYPES = frozenset({
    "aws_security_group",
    "aws_vpc_security_group_ingress_rule",
    "aws_vpc_security_group_egress_rule",
    "aws_s3_bucket",
    "aws_s3_bucket_public_access_block",
    "aws_s3_bucket_server_side_encryption_configuration",
    "aws_instance",
})


@dataclass(frozen=True)
class TerraformStateAdaptation:
    snapshots: list[ResourceSnapshot]
    diagnostics: tuple[CollectionDiagnostic, ...]


def adapt_terraform_state(payload: dict[str, Any]) -> list[ResourceSnapshot]:
    """Normalize Terraform state into resource snapshots, discarding diagnostics."""
    return adapt_terraform_state_with_diagnostics(payload).snapshots


def adapt_terraform_state_with_diagnostics(payload: dict[str, Any]) -> TerraformStateAdaptation:
    """Normalize managed resources and expose intentional unsupported-resource skips."""
    root_module = payload.get("values", {}).get("root_module", {})
    resources = list(_walk_resources(root_module))
    bucket_settings = _collect_bucket_settings(resources)
    parent_security_group_ids = {
        values["id"]
        for resource in resources
        if resource.get("mode") == "managed"
        and resource.get("type") == "aws_security_group"
        and (values := resource.get("values", {})).get("id")
    }
    security_group_rules, rule_diagnostics = _collect_security_group_rules(resources, parent_security_group_ids)
    snapshots: list[ResourceSnapshot] = []
    diagnostics = list(rule_diagnostics)

    for resource in resources:
        if resource.get("mode") != "managed":
            continue
        resource_type = resource.get("type")
        values = resource.get("values", {})
        if resource_type == "aws_security_group":
            snapshots.append(_security_group(resource, values, security_group_rules.get(values.get("id"), {})))
        elif resource_type == "aws_s3_bucket":
            snapshots.append(_s3_bucket(resource, values, bucket_settings.get(values.get("bucket") or values.get("id"), {})))
        elif resource_type == "aws_instance":
            snapshots.append(_instance(resource, values))
        elif resource_type not in _SUPPORTED_RESOURCE_TYPES:
            diagnostics.append(CollectionDiagnostic(
                source="terraform_state",
                resource_address=resource.get("address"),
                message=f"Skipped unsupported Terraform resource type: {resource_type or 'unknown'}.",
            ))
    return TerraformStateAdaptation(snapshots, tuple(diagnostics))


def _walk_resources(module: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield from module.get("resources", [])
    for child in module.get("child_modules", []):
        yield from _walk_resources(child)


def _collect_bucket_settings(resources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    settings: dict[str, dict[str, Any]] = {}
    for resource in resources:
        values = resource.get("values", {})
        bucket = values.get("bucket")
        if not bucket:
            continue
        if resource.get("type") == "aws_s3_bucket_public_access_block":
            settings.setdefault(bucket, {})["public_access_block"] = {
                "block_public_acls": bool(values.get("block_public_acls")),
                "ignore_public_acls": bool(values.get("ignore_public_acls")),
                "block_public_policy": bool(values.get("block_public_policy")),
                "restrict_public_buckets": bool(values.get("restrict_public_buckets")),
            }
        elif resource.get("type") == "aws_s3_bucket_server_side_encryption_configuration":
            rule = (values.get("rule") or [{}])[0]
            settings.setdefault(bucket, {})["encryption"] = rule.get(
                "apply_server_side_encryption_by_default", {}
            )
    return settings


def _collect_security_group_rules(
    resources: list[dict[str, Any]],
    parent_security_group_ids: set[str],
) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], list[CollectionDiagnostic]]:
    settings: dict[str, dict[str, list[dict[str, Any]]]] = {}
    diagnostics: list[CollectionDiagnostic] = []
    for resource in resources:
        if resource.get("mode") != "managed" or resource.get("type") not in {
            "aws_vpc_security_group_ingress_rule",
            "aws_vpc_security_group_egress_rule",
        }:
            continue
        values = resource.get("values", {})
        security_group_id = values.get("security_group_id")
        if security_group_id not in parent_security_group_ids:
            diagnostics.append(CollectionDiagnostic(
                source="terraform_state",
                resource_address=resource.get("address"),
                message="Skipped security-group rule because its parent security group is not supported in this state.",
            ))
            continue
        direction = "ingress" if resource["type"] == "aws_vpc_security_group_ingress_rule" else "egress"
        settings.setdefault(security_group_id, {"ingress": [], "egress": []})[direction].append(
            _normalize_terraform_security_group_rule(values)
        )
    return settings, diagnostics


def _security_group(
    resource: dict[str, Any],
    values: dict[str, Any],
    standalone_rules: dict[str, list[dict[str, Any]]],
) -> ResourceSnapshot:
    ingress = [_normalize_terraform_security_group_rule(rule) for rule in values.get("ingress", [])]
    ingress.extend(standalone_rules.get("ingress", []))
    egress = [_normalize_terraform_security_group_rule(rule) for rule in values.get("egress", [])]
    egress.extend(standalone_rules.get("egress", []))
    return ResourceSnapshot(
        identity=ResourceIdentity("aws", "security_group", values.get("group_name") or resource["name"]),
        category=ResourceCategory.NETWORKING,
        attributes={
            "vpc_id": values.get("vpc_id"),
            "ingress": canonicalize_security_group_rules(ingress),
            "egress": canonicalize_security_group_rules(egress),
            "tags": values.get("tags", {}),
        },
        source_address=resource.get("address"),
    )


def _normalize_terraform_security_group_rule(values: dict[str, Any]) -> dict[str, Any]:
    cidr_ipv4 = values.get("cidr_ipv4")
    cidr_ipv6 = values.get("cidr_ipv6")
    prefix_list_id = values.get("prefix_list_id")
    referenced_group = values.get("referenced_security_group_id")
    return {
        "from_port": values.get("from_port"),
        "to_port": values.get("to_port"),
        "protocol": values.get("ip_protocol", values.get("protocol")),
        "cidr_blocks": sorted((values.get("cidr_blocks") or []) + ([cidr_ipv4] if cidr_ipv4 else [])),
        "ipv6_cidr_blocks": sorted((values.get("ipv6_cidr_blocks") or []) + ([cidr_ipv6] if cidr_ipv6 else [])),
        "prefix_list_ids": sorted((values.get("prefix_list_ids") or []) + ([prefix_list_id] if prefix_list_id else [])),
        "security_group_ids": sorted((values.get("security_groups") or []) + ([referenced_group] if referenced_group else [])),
    }


def _s3_bucket(resource: dict[str, Any], values: dict[str, Any], settings: dict[str, Any]) -> ResourceSnapshot:
    return ResourceSnapshot(
        identity=ResourceIdentity("aws", "s3_bucket", values.get("bucket") or resource["name"]),
        category=ResourceCategory.STORAGE,
        attributes={
            "bucket": values.get("bucket") or values.get("id"),
            "tags": values.get("tags", {}),
            "public_access_block": settings.get("public_access_block", {}),
            "encryption": settings.get("encryption", {}),
        },
        source_address=resource.get("address"),
    )


def _instance(resource: dict[str, Any], values: dict[str, Any]) -> ResourceSnapshot:
    return ResourceSnapshot(
        identity=ResourceIdentity("aws", "instance", values.get("tags", {}).get("Name") or values.get("id") or resource["name"]),
        category=ResourceCategory.COMPUTE,
        attributes={
            "instance_type": values.get("instance_type"),
            "ami": values.get("ami"),
            "subnet_id": values.get("subnet_id"),
            "associate_public_ip_address": bool(values.get("associate_public_ip_address")),
            "security_group_ids": sorted(values.get("vpc_security_group_ids", [])),
            "tags": values.get("tags", {}),
        },
        source_address=resource.get("address"),
    )
