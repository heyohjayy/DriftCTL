"""Translate boto3 response-shaped inventory into normalized snapshots."""

from __future__ import annotations

import json
from typing import Any

from driftctl.adapters.security_group_rules import canonicalize_security_group_rules
from driftctl.models import ResourceCategory, ResourceIdentity, ResourceSnapshot


def adapt_boto3_inventory(payload: dict[str, Any]) -> list[ResourceSnapshot]:
    snapshots = [_security_group(x) for x in payload.get("SecurityGroups", [])]
    snapshots += [_s3(x) for x in payload.get("Buckets", [])]
    snapshots += [_network(x, "vpc", {"cidr_block": x.get("CidrBlock"), "tags": _tags(x.get("Tags", []))}) for x in payload.get("Vpcs", [])]
    snapshots += [_network(x, "subnet", {"vpc_id": x.get("VpcId"), "cidr_block": x.get("CidrBlock"), "availability_zone": x.get("AvailabilityZone"), "map_public_ip_on_launch": bool(x.get("MapPublicIpOnLaunch")), "tags": _tags(x.get("Tags", []))}) for x in payload.get("Subnets", [])]
    snapshots += [_network(x, "internet_gateway", {"vpc_id": next((a.get("VpcId") for a in x.get("Attachments", []) if a.get("State") == "available"), None), "tags": _tags(x.get("Tags", []))}) for x in payload.get("InternetGateways", [])]
    snapshots += [_route_table(x) for x in payload.get("RouteTables", [])]
    snapshots += [_nacl(x) for x in payload.get("NetworkAcls", [])]
    for reservation in payload.get("Reservations", []): snapshots += [_instance(x) for x in reservation.get("Instances", [])]
    snapshots += [_role(x) for x in payload.get("IamRoles", [])]
    snapshots += [_profile(x) for x in payload.get("InstanceProfiles", [])]
    zones = [_zone(x) for x in payload.get("HostedZones", [])]; snapshots += zones
    zone_tags = {x["Id"]: _tags(x.get("Tags", [])) for x in payload.get("HostedZones", [])}
    zone_names = {x["Id"]: x.get("Name", "").rstrip(".") for x in payload.get("HostedZones", [])}
    for zone_id, records in payload.get("RecordSets", {}).items():
        if zone_id in zone_names: snapshots += [_record(x, zone_names[zone_id], zone_tags[zone_id]) for x in records]
    return snapshots


def _tags(tags: list[dict[str, str]]) -> dict[str, str]: return {x["Key"]: x["Value"] for x in tags if "Key" in x and "Value" in x}
def _name(tags: dict[str, str], fallback: str) -> str: return tags.get("Name") or fallback
def _network(raw: dict[str, Any], kind: str, attrs: dict[str, Any]) -> ResourceSnapshot:
    tags = attrs.get("tags", {}); fallback = raw.get("VpcId") or raw.get("SubnetId") or raw.get("InternetGatewayId") or raw.get("RouteTableId") or raw.get("NetworkAclId") or "unknown"; return ResourceSnapshot(ResourceIdentity("aws", kind, _name(tags, fallback)), ResourceCategory.NETWORKING, attrs)


def _security_group(group: dict[str, Any]) -> ResourceSnapshot:
    normalize = lambda p: {"from_port": p.get("FromPort"), "to_port": p.get("ToPort"), "protocol": p.get("IpProtocol"), "cidr_blocks": sorted(x["CidrIp"] for x in p.get("IpRanges", []) if "CidrIp" in x), "ipv6_cidr_blocks": sorted(x["CidrIpv6"] for x in p.get("Ipv6Ranges", []) if "CidrIpv6" in x), "prefix_list_ids": sorted(x["PrefixListId"] for x in p.get("PrefixListIds", []) if "PrefixListId" in x), "security_group_ids": sorted(x["GroupId"] for x in p.get("UserIdGroupPairs", []) if "GroupId" in x)}
    return ResourceSnapshot(ResourceIdentity("aws", "security_group", group.get("GroupName") or group["GroupId"]), ResourceCategory.NETWORKING, {"vpc_id": group.get("VpcId"), "ingress": canonicalize_security_group_rules(normalize(p) for p in group.get("IpPermissions", [])), "egress": canonicalize_security_group_rules(normalize(p) for p in group.get("IpPermissionsEgress", [])), "tags": _tags(group.get("Tags", []))})


def _s3(bucket: dict[str, Any]) -> ResourceSnapshot:
    pab = bucket.get("PublicAccessBlockConfiguration", {}); rules = bucket.get("BucketEncryption", {}).get("Rules", []); encryption = rules[0].get("ApplyServerSideEncryptionByDefault", {}) if rules else {}
    return ResourceSnapshot(ResourceIdentity("aws", "s3_bucket", bucket["Name"]), ResourceCategory.STORAGE, {"bucket": bucket["Name"], "tags": _tags(bucket.get("Tags", [])), "public_access_block": {"block_public_acls": bool(pab.get("BlockPublicAcls")), "ignore_public_acls": bool(pab.get("IgnorePublicAcls")), "block_public_policy": bool(pab.get("BlockPublicPolicy")), "restrict_public_buckets": bool(pab.get("RestrictPublicBuckets"))}, "encryption": encryption})


def _instance(x: dict[str, Any]) -> ResourceSnapshot:
    tags = _tags(x.get("Tags", [])); return ResourceSnapshot(ResourceIdentity("aws", "instance", _name(tags, x["InstanceId"])), ResourceCategory.COMPUTE, {"instance_type": x.get("InstanceType"), "ami": x.get("ImageId"), "subnet_id": x.get("SubnetId"), "associate_public_ip_address": bool(x.get("PublicIpAddress")), "security_group_ids": sorted(g["GroupId"] for g in x.get("SecurityGroups", [])), "tags": tags})


def _route_table(x: dict[str, Any]) -> ResourceSnapshot:
    tags = _tags(x.get("Tags", [])); routes = []
    for route in x.get("Routes", []):
        if route.get("GatewayId") == "local" or route.get("Origin") == "CreateRouteTable": continue
        target_key = next((key for key in ("GatewayId", "NatGatewayId", "TransitGatewayId", "VpcPeeringConnectionId", "NetworkInterfaceId", "InstanceId") if route.get(key)), None); target = route.get(target_key) if target_key else None
        routes.append({"destination_ipv4": route.get("DestinationCidrBlock"), "destination_ipv6": route.get("DestinationIpv6CidrBlock"), "target": target, "target_type": "internet_gateway" if target_key == "GatewayId" and str(target).startswith("igw-") else None})
    associations = [{"subnet_id": a.get("SubnetId")} for a in x.get("Associations", []) if a.get("SubnetId")]
    return ResourceSnapshot(ResourceIdentity("aws", "route_table", _name(tags, x["RouteTableId"])), ResourceCategory.NETWORKING, {"vpc_id": x.get("VpcId"), "routes": sorted(routes, key=repr), "associations": sorted(associations, key=repr), "tags": tags})


def _nacl(x: dict[str, Any]) -> ResourceSnapshot:
    tags = _tags(x.get("Tags", [])); entries = [{"egress": bool(e.get("Egress")), "rule_number": e.get("RuleNumber"), "protocol": str(e.get("Protocol")), "action": e.get("RuleAction"), "cidr_block": e.get("CidrBlock"), "ipv6_cidr_block": e.get("Ipv6CidrBlock")} for e in x.get("Entries", [])]; associations = [{"subnet_id": a.get("SubnetId")} for a in x.get("Associations", [])]
    return ResourceSnapshot(ResourceIdentity("aws", "network_acl", _name(tags, x["NetworkAclId"])), ResourceCategory.NETWORKING, {"vpc_id": x.get("VpcId"), "entries": sorted(entries, key=repr), "associations": sorted(associations, key=repr), "tags": tags})


def _role(x: dict[str, Any]) -> ResourceSnapshot:
    tags = _tags(x.get("Tags", [])); return ResourceSnapshot(ResourceIdentity("aws", "iam_role", x["RoleName"]), ResourceCategory.IAM, {"trust_policy": _policy(x.get("AssumeRolePolicyDocument")), "managed_policy_arns": sorted(x.get("ManagedPolicyArns", [])), "inline_policies": sorted(x.get("InlinePolicies", []), key=repr), "tags": tags})
def _profile(x: dict[str, Any]) -> ResourceSnapshot: return ResourceSnapshot(ResourceIdentity("aws", "iam_instance_profile", x["InstanceProfileName"]), ResourceCategory.IAM, {"roles": sorted(r["RoleName"] for r in x.get("Roles", [])), "tags": _tags(x.get("Tags", []))})
def _zone(x: dict[str, Any]) -> ResourceSnapshot: return ResourceSnapshot(ResourceIdentity("aws", "route53_hosted_zone", x.get("Name", "").rstrip(".")), ResourceCategory.OTHER, {"private_zone": bool(x.get("Config", {}).get("PrivateZone")), "tags": _tags(x.get("Tags", []))})
def _record(x: dict[str, Any], zone: str, tags: dict[str, str]) -> ResourceSnapshot:
    name, typ = x.get("Name", "").rstrip("."), x.get("Type"); alias = x.get("AliasTarget") or {}; return ResourceSnapshot(ResourceIdentity("aws", "route53_record", f"{zone}|{name}|{typ}"), ResourceCategory.OTHER, {"zone": zone, "name": name, "type": typ, "ttl": x.get("TTL"), "records": sorted(v["Value"] for v in x.get("ResourceRecords", []) if "Value" in v), "alias": [alias] if alias else [], "tags": tags}, provider_managed=name == zone and typ in {"SOA", "NS"})
def _policy(value: Any) -> Any:
    if isinstance(value, str):
        try: return json.loads(value)
        except json.JSONDecodeError: return value
    return value or {}
