"""Translate boto3 response-shaped inventory into domain snapshots."""

from __future__ import annotations

from typing import Any

from driftctl.adapters.security_group_rules import canonicalize_security_group_rules
from driftctl.models import ResourceCategory, ResourceIdentity, ResourceSnapshot


def adapt_boto3_inventory(payload: dict[str, Any]) -> list[ResourceSnapshot]:
    snapshots = [_security_group(group) for group in payload.get("SecurityGroups", [])]
    snapshots.extend(_s3_bucket(bucket) for bucket in payload.get("Buckets", []))
    for reservation in payload.get("Reservations", []):
        snapshots.extend(_instance(instance) for instance in reservation.get("Instances", []))
    return snapshots


def _tags(raw_tags: list[dict[str, str]]) -> dict[str, str]:
    return {tag["Key"]: tag["Value"] for tag in raw_tags if "Key" in tag and "Value" in tag}


def _security_group(group: dict[str, Any]) -> ResourceSnapshot:
    ingress = canonicalize_security_group_rules(
        _normalize_security_group_permission(permission) for permission in group.get("IpPermissions", [])
    )
    egress = canonicalize_security_group_rules(
        _normalize_security_group_permission(permission) for permission in group.get("IpPermissionsEgress", [])
    )
    return ResourceSnapshot(
        identity=ResourceIdentity("aws", "security_group", group.get("GroupName") or group["GroupId"]),
        category=ResourceCategory.NETWORKING,
        attributes={
            "vpc_id": group.get("VpcId"),
            "ingress": ingress,
            "egress": egress,
            "tags": _tags(group.get("Tags", [])),
        },
    )


def _normalize_security_group_permission(permission: dict[str, Any]) -> dict[str, Any]:
    return {
        "from_port": permission.get("FromPort"),
        "to_port": permission.get("ToPort"),
        "protocol": permission.get("IpProtocol"),
        "cidr_blocks": sorted(entry["CidrIp"] for entry in permission.get("IpRanges", []) if "CidrIp" in entry),
        "ipv6_cidr_blocks": sorted(entry["CidrIpv6"] for entry in permission.get("Ipv6Ranges", []) if "CidrIpv6" in entry),
        "prefix_list_ids": sorted(entry["PrefixListId"] for entry in permission.get("PrefixListIds", []) if "PrefixListId" in entry),
        "security_group_ids": sorted(entry["GroupId"] for entry in permission.get("UserIdGroupPairs", []) if "GroupId" in entry),
    }


def _s3_bucket(bucket: dict[str, Any]) -> ResourceSnapshot:
    public_access = bucket.get("PublicAccessBlockConfiguration", {})
    normalized_public_access = {
        "block_public_acls": bool(public_access.get("BlockPublicAcls")),
        "ignore_public_acls": bool(public_access.get("IgnorePublicAcls")),
        "block_public_policy": bool(public_access.get("BlockPublicPolicy")),
        "restrict_public_buckets": bool(public_access.get("RestrictPublicBuckets")),
    }
    encryption = bucket.get("BucketEncryption", {})
    rules = encryption.get("Rules", [])
    default_encryption = rules[0].get("ApplyServerSideEncryptionByDefault", {}) if rules else {}
    return ResourceSnapshot(
        identity=ResourceIdentity("aws", "s3_bucket", bucket["Name"]),
        category=ResourceCategory.STORAGE,
        attributes={
            "bucket": bucket["Name"],
            "tags": _tags(bucket.get("Tags", [])),
            "public_access_block": normalized_public_access,
            "encryption": default_encryption,
        },
    )


def _instance(instance: dict[str, Any]) -> ResourceSnapshot:
    tags = _tags(instance.get("Tags", []))
    return ResourceSnapshot(
        identity=ResourceIdentity("aws", "instance", tags.get("Name") or instance["InstanceId"]),
        category=ResourceCategory.COMPUTE,
        attributes={
            "instance_type": instance.get("InstanceType"),
            "ami": instance.get("ImageId"),
            "subnet_id": instance.get("SubnetId"),
            "associate_public_ip_address": bool(instance.get("PublicIpAddress")),
            "security_group_ids": sorted(group["GroupId"] for group in instance.get("SecurityGroups", [])),
            "tags": tags,
        },
    )
