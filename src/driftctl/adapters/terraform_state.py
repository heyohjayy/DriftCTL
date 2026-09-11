"""Translate terraform show -json-style state into domain snapshots."""

from __future__ import annotations

from typing import Any, Iterable

from driftctl.models import ResourceCategory, ResourceIdentity, ResourceSnapshot


def adapt_terraform_state(payload: dict[str, Any]) -> list[ResourceSnapshot]:
    """Normalize managed AWS resources and attach S3 companion resources by bucket."""
    root_module = payload.get("values", {}).get("root_module", {})
    resources = list(_walk_resources(root_module))
    bucket_settings = _collect_bucket_settings(resources)
    snapshots: list[ResourceSnapshot] = []

    for resource in resources:
        if resource.get("mode") != "managed":
            continue
        resource_type = resource.get("type")
        values = resource.get("values", {})
        if resource_type == "aws_security_group":
            snapshots.append(_security_group(resource, values))
        elif resource_type == "aws_s3_bucket":
            snapshots.append(_s3_bucket(resource, values, bucket_settings.get(values.get("bucket") or values.get("id"), {})))
        elif resource_type == "aws_instance":
            snapshots.append(_instance(resource, values))
    return snapshots


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


def _security_group(resource: dict[str, Any], values: dict[str, Any]) -> ResourceSnapshot:
    ingress = [
        {
            "from_port": rule.get("from_port"),
            "to_port": rule.get("to_port"),
            "protocol": rule.get("protocol"),
            "cidr_blocks": sorted(rule.get("cidr_blocks", [])),
            "ipv6_cidr_blocks": sorted(rule.get("ipv6_cidr_blocks", [])),
        }
        for rule in values.get("ingress", [])
    ]
    return ResourceSnapshot(
        identity=ResourceIdentity("aws", "security_group", values.get("group_name") or resource["name"]),
        category=ResourceCategory.NETWORKING,
        attributes={"vpc_id": values.get("vpc_id"), "ingress": ingress, "tags": values.get("tags", {})},
        source_address=resource.get("address"),
    )


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
