"""Translate boto3 response-shaped inventory into normalized snapshots."""

from __future__ import annotations

import json
from typing import Any

from driftctl.adapters.ecs import (
    assign_public_ip,
    capacity_provider_strategy,
    cluster_settings,
    container_definitions,
    runtime_platform,
    task_definition_ref,
)
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
    subnets = {x.get("SubnetId"): x.get("VpcId") for x in payload.get("Subnets", [])}
    snapshots += [_nat_gateway(x, subnets) for x in payload.get("NatGateways", []) if x.get("State") != "deleted"]
    raw_load_balancers = [x for x in payload.get("LoadBalancers", []) if x.get("Type", "application") == "application"]
    load_balancers = [_load_balancer(x) for x in raw_load_balancers]; snapshots += load_balancers
    load_balancer_names = {x.get("LoadBalancerArn"): _resource_name(x, "LoadBalancerName") for x in raw_load_balancers}
    load_balancer_tags = {x.get("LoadBalancerArn"): _tags(x.get("Tags", [])) for x in raw_load_balancers}
    raw_target_groups = payload.get("TargetGroups", [])
    target_groups = [_target_group(x) for x in raw_target_groups]; snapshots += target_groups
    target_group_names = dict(payload.get("TargetGroupReferences", {})); target_group_names.update({x.get("TargetGroupArn"): _resource_name(x, "TargetGroupName") for x in raw_target_groups})
    listener_names: dict[str, str] = {}
    for load_balancer_arn, listeners in payload.get("Listeners", {}).items():
        for listener in listeners:
            snapshot = _listener(listener, load_balancer_names.get(load_balancer_arn, load_balancer_arn), load_balancer_tags.get(load_balancer_arn, {}), target_group_names)
            snapshots.append(snapshot); listener_names[listener.get("ListenerArn")] = snapshot.identity.name
    for listener_arn, rules in payload.get("ListenerRules", {}).items():
        listener_name = listener_names.get(listener_arn)
        if listener_name: snapshots += [_listener_rule(x, listener_name, load_balancer_tags.get(_listener_load_balancer_arn(listener_arn, payload), {}), target_group_names) for x in rules if not x.get("IsDefault")]
    snapshots += [_db_instance(x) for x in payload.get("DBInstances", [])]
    raw_clusters = payload.get("ECSClusters", [])
    cluster_names = {x.get("clusterArn"): x.get("clusterName") for x in raw_clusters}
    cluster_tags = {x.get("clusterArn"): _tags(x.get("tags", x.get("Tags", []))) for x in raw_clusters}
    task_tags = _ecs_task_definition_tags(payload.get("ECSServices", []), cluster_tags)
    snapshots += [_ecs_cluster(x) for x in raw_clusters]
    snapshots += [_ecs_task_definition(x, task_tags) for x in payload.get("ECSTaskDefinitions", [])]
    snapshots += [_ecs_service(x, cluster_names, cluster_tags, target_group_names) for x in payload.get("ECSServices", [])]
    snapshots += [_log_group(x) for x in payload.get("LogGroups", [])]
    snapshots += [_role(x) for x in payload.get("IamRoles", [])]
    snapshots += [_profile(x) for x in payload.get("InstanceProfiles", [])]
    zones = [_zone(x) for x in payload.get("HostedZones", [])]; snapshots += zones
    zone_tags = {x["Id"]: _tags(x.get("Tags", [])) for x in payload.get("HostedZones", [])}
    zone_names = {x["Id"]: x.get("Name", "").rstrip(".") for x in payload.get("HostedZones", [])}
    for zone_id, records in payload.get("RecordSets", {}).items():
        if zone_id in zone_names: snapshots += [_record(x, zone_names[zone_id], zone_tags[zone_id]) for x in records]
    return snapshots


def _tags(tags: list[dict[str, str]] | dict[str, str]) -> dict[str, str]:
    if isinstance(tags, dict): return dict(tags)
    return {(x.get("Key") or x.get("key")): (x.get("Value") or x.get("value", "")) for x in tags if x.get("Key") or x.get("key")}
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


def _resource_name(x: dict[str, Any], field: str) -> str:
    tags = _tags(x.get("Tags", [])); return _name(tags, x.get(field, "unknown"))
def _nat_gateway(x: dict[str, Any], subnets: dict[str, Any]) -> ResourceSnapshot:
    tags = _tags(x.get("Tags", [])); subnet = x.get("SubnetId"); return ResourceSnapshot(ResourceIdentity("aws", "nat_gateway", _name(tags, x.get("NatGatewayId", "unknown"))), ResourceCategory.NETWORKING, {"subnet_id": subnet, "vpc_id": x.get("VpcId") or subnets.get(subnet), "allocation_ids": sorted(address.get("AllocationId") for address in x.get("NatGatewayAddresses", []) if address.get("AllocationId")), "connectivity_type": x.get("ConnectivityType") or "public", "state": x.get("State"), "tags": tags})
def _load_balancer(x: dict[str, Any]) -> ResourceSnapshot:
    tags = _tags(x.get("Tags", [])); return ResourceSnapshot(ResourceIdentity("aws", "application_load_balancer", _name(tags, x.get("LoadBalancerName", "unknown"))), ResourceCategory.NETWORKING, {"scheme": x.get("Scheme"), "ip_address_type": x.get("IpAddressType") or "ipv4", "subnet_ids": sorted(availability_zone.get("SubnetId") for availability_zone in x.get("AvailabilityZones", []) if availability_zone.get("SubnetId")), "security_group_ids": sorted(x.get("SecurityGroups", [])), "tags": tags})
def _target_group(x: dict[str, Any]) -> ResourceSnapshot:
    tags = _tags(x.get("Tags", [])); return ResourceSnapshot(ResourceIdentity("aws", "target_group", _name(tags, x.get("TargetGroupName", "unknown"))), ResourceCategory.NETWORKING, {"vpc_id": x.get("VpcId"), "protocol": x.get("Protocol"), "port": x.get("Port"), "target_type": x.get("TargetType") or "instance", "health_check": _health_check_live(x), "tags": tags})
def _listener(x: dict[str, Any], load_balancer: str, inherited_tags: dict[str, str], target_groups: dict[str, str]) -> ResourceSnapshot:
    tags = _tags(x.get("Tags", [])) or inherited_tags; return ResourceSnapshot(ResourceIdentity("aws", "load_balancer_listener", f"{load_balancer}|{x.get('Protocol')}|{x.get('Port')}"), ResourceCategory.NETWORKING, {"load_balancer": load_balancer, "protocol": x.get("Protocol"), "port": x.get("Port"), "ssl_policy": _none_if_blank(x.get("SslPolicy")), "certificate_arn": next((certificate.get("CertificateArn") for certificate in x.get("Certificates", []) if certificate.get("IsDefault")), None), "default_actions": _actions_live(x.get("DefaultActions", []), target_groups), "tags": tags})
def _listener_rule(x: dict[str, Any], listener: str, inherited_tags: dict[str, str], target_groups: dict[str, str]) -> ResourceSnapshot:
    tags = _tags(x.get("Tags", [])) or inherited_tags; return ResourceSnapshot(ResourceIdentity("aws", "load_balancer_listener_rule", f"{listener}|{x.get('Priority')}"), ResourceCategory.NETWORKING, {"listener": listener, "priority": str(x.get("Priority")), "conditions": _conditions_live(x.get("Conditions", [])), "actions": _actions_live(x.get("Actions", []), target_groups), "tags": tags})
def _listener_load_balancer_arn(listener_arn: str, payload: dict[str, Any]) -> str | None:
    for load_balancer_arn, listeners in payload.get("Listeners", {}).items():
        if any(listener.get("ListenerArn") == listener_arn for listener in listeners): return load_balancer_arn
    return None
def _health_check_live(x: dict[str, Any]) -> dict[str, Any]: return {"enabled": bool(x.get("HealthCheckEnabled", True)), "protocol": x.get("HealthCheckProtocol"), "port": x.get("HealthCheckPort"), "path": x.get("HealthCheckPath"), "interval": x.get("HealthCheckIntervalSeconds"), "timeout": x.get("HealthCheckTimeoutSeconds"), "healthy_threshold": x.get("HealthyThresholdCount"), "unhealthy_threshold": x.get("UnhealthyThresholdCount"), "matcher": x.get("Matcher", {}).get("HttpCode")}
def _actions_live(actions: list[dict[str, Any]], target_groups: dict[str, str]) -> list[dict[str, Any]]:
    return sorted([{"type": action.get("Type"), "target_groups": _forward_live(action, target_groups), "redirect": _redirect_live(action.get("RedirectConfig")), "fixed_response": _fixed_response_live(action.get("FixedResponseConfig"))} for action in actions], key=repr)
def _redirect_live(value: dict[str, Any] | None) -> list[dict[str, Any]]: return [] if not value else [{"protocol": value.get("Protocol"), "host": value.get("Host"), "port": value.get("Port"), "path": value.get("Path"), "query": value.get("Query"), "status_code": value.get("StatusCode")}]
def _fixed_response_live(value: dict[str, Any] | None) -> list[dict[str, Any]]: return [] if not value else [{"content_type": value.get("ContentType"), "message_body": value.get("MessageBody"), "status_code": value.get("StatusCode")}]
def _forward_live(action: dict[str, Any], target_groups: dict[str, str]) -> list[dict[str, Any]]:
    values = []
    for target in action.get("ForwardConfig", {}).get("TargetGroups", []):
        arn = target.get("TargetGroupArn"); values.append({"target_group": target_groups.get(arn, arn), "weight": target.get("Weight")})
    if not values and action.get("TargetGroupArn"): values.append({"target_group": target_groups.get(action["TargetGroupArn"], action["TargetGroupArn"]), "weight": None})
    return sorted(values, key=repr)
def _conditions_live(conditions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = []
    for item in conditions:
        config = item.get("HostHeaderConfig") or item.get("PathPatternConfig") or {}; values.append({"field": item.get("Field"), "values": sorted(item.get("Values") or config.get("Values", []))})
    return sorted(values, key=repr)
def _db_instance(x: dict[str, Any]) -> ResourceSnapshot:
    tags = _tags(x.get("Tags", [])); return ResourceSnapshot(ResourceIdentity("aws", "rds_db_instance", _name(tags, x.get("DBInstanceIdentifier", "unknown"))), ResourceCategory.DATABASE, {"engine": x.get("Engine"), "engine_version": x.get("EngineVersion"), "instance_class": x.get("DBInstanceClass"), "allocated_storage": x.get("AllocatedStorage"), "storage_type": x.get("StorageType"), "storage_encrypted": bool(x.get("StorageEncrypted")), "publicly_accessible": bool(x.get("PubliclyAccessible")), "vpc_security_group_ids": sorted(group.get("VpcSecurityGroupId") for group in x.get("VpcSecurityGroups", []) if group.get("VpcSecurityGroupId")), "db_subnet_group_name": x.get("DBSubnetGroup", {}).get("DBSubnetGroupName"), "backup_retention_period": x.get("BackupRetentionPeriod"), "deletion_protection": bool(x.get("DeletionProtection")), "multi_az": bool(x.get("MultiAZ")), "port": x.get("Endpoint", {}).get("Port") or x.get("Port"), "copy_tags_to_snapshot": bool(x.get("CopyTagsToSnapshot")), "tags": tags})


def _ecs_cluster(x: dict[str, Any]) -> ResourceSnapshot:
    return ResourceSnapshot(
        ResourceIdentity("aws", "ecs_cluster", x.get("clusterName") or str(x.get("clusterArn", "unknown")).rsplit("/", 1)[-1]),
        ResourceCategory.COMPUTE,
        {"settings": cluster_settings(x.get("settings")), "tags": _tags(x.get("tags", x.get("Tags", [])))},
    )


def _ecs_task_definition_tags(services: list[dict[str, Any]], cluster_tags: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    tags: dict[str, dict[str, str]] = {}
    for service in services:
        reference = task_definition_ref(service.get("taskDefinition"))
        if reference:
            own_tags = _tags(service.get("tags", service.get("Tags", [])))
            tags[reference] = own_tags or cluster_tags.get(service.get("clusterArn"), {})
    return tags


def _ecs_task_definition(x: dict[str, Any], inherited_tags: dict[str, dict[str, str]]) -> ResourceSnapshot:
    ephemeral = x.get("ephemeralStorage") or {}
    identity = task_definition_ref(x.get("taskDefinitionArn")) or f"{x.get('family')}:{x.get('revision')}"
    return ResourceSnapshot(
        ResourceIdentity("aws", "ecs_task_definition", identity),
        ResourceCategory.COMPUTE,
        {
            "family": x.get("family"),
            "revision": x.get("revision"),
            "network_mode": x.get("networkMode"),
            "requires_compatibilities": sorted(x.get("requiresCompatibilities", [])),
            "cpu": _string_or_none(x.get("cpu")),
            "memory": _string_or_none(x.get("memory")),
            "execution_role_arn": x.get("executionRoleArn"),
            "task_role_arn": x.get("taskRoleArn"),
            "runtime_platform": runtime_platform(x.get("runtimePlatform")),
            "ephemeral_storage_gib": ephemeral.get("sizeInGiB"),
            "container_definitions": container_definitions(x.get("containerDefinitions")),
            "tags": _tags(x.get("tags", x.get("Tags", []))) or inherited_tags.get(identity, {}),
        },
    )


def _ecs_service(
    x: dict[str, Any],
    cluster_names: dict[str, str],
    cluster_tags: dict[str, dict[str, str]],
    target_groups: dict[str, str],
) -> ResourceSnapshot:
    cluster_ref = x.get("clusterArn") or x.get("cluster") or "default"
    cluster = cluster_names.get(cluster_ref, str(cluster_ref).rsplit("/", 1)[-1])
    network = x.get("networkConfiguration", {}).get("awsvpcConfiguration", {})
    deployment = x.get("deploymentConfiguration", {})
    tags = _tags(x.get("tags", x.get("Tags", []))) or cluster_tags.get(cluster_ref, {})
    return ResourceSnapshot(
        ResourceIdentity("aws", "ecs_service", f"{cluster}|{x.get('serviceName')}"),
        ResourceCategory.COMPUTE,
        {
            "cluster": cluster,
            "task_definition": task_definition_ref(x.get("taskDefinition")),
            "desired_count": x.get("desiredCount"),
            "launch_type": x.get("launchType"),
            "capacity_provider_strategy": capacity_provider_strategy(x.get("capacityProviderStrategy")),
            "network_configuration": {
                "subnets": sorted(network.get("subnets", [])),
                "security_groups": sorted(network.get("securityGroups", [])),
                "assign_public_ip": assign_public_ip(network.get("assignPublicIp")),
            },
            "deployment": {
                "minimum_healthy_percent": deployment.get("minimumHealthyPercent", 100),
                "maximum_percent": deployment.get("maximumPercent", 200),
                "circuit_breaker_enable": deployment.get("deploymentCircuitBreaker", {}).get("enable", False),
                "circuit_breaker_rollback": deployment.get("deploymentCircuitBreaker", {}).get("rollback", False),
            },
            "scheduling_strategy": x.get("schedulingStrategy") or "REPLICA",
            "enable_execute_command": bool(x.get("enableExecuteCommand")),
            "load_balancers": _ecs_load_balancers_live(x.get("loadBalancers", []), target_groups),
            "tags": tags,
        },
    )


def _ecs_load_balancers_live(values: list[dict[str, Any]], target_groups: dict[str, str]) -> list[dict[str, Any]]:
    return sorted(
        ({
            "target_group": target_groups.get(item.get("targetGroupArn"), item.get("targetGroupArn")),
            "container_name": item.get("containerName"),
            "container_port": item.get("containerPort"),
        } for item in values),
        key=repr,
    )


def _log_group(x: dict[str, Any]) -> ResourceSnapshot:
    return ResourceSnapshot(
        ResourceIdentity("aws", "cloudwatch_log_group", x.get("logGroupName", "unknown")),
        ResourceCategory.OTHER,
        {
            "retention_in_days": x.get("retentionInDays"),
            "kms_key_id": x.get("kmsKeyId"),
            "log_group_class": x.get("logGroupClass") or "STANDARD",
            "tags": _tags(x.get("tags", x.get("Tags", {}))),
        },
    )


def _string_or_none(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _route_table(x: dict[str, Any]) -> ResourceSnapshot:
    tags = _tags(x.get("Tags", [])); routes = []
    for route in x.get("Routes", []):
        if route.get("GatewayId") == "local" or route.get("Origin") == "CreateRouteTable": continue
        target_key = next((key for key in ("GatewayId", "NatGatewayId", "TransitGatewayId", "VpcPeeringConnectionId", "NetworkInterfaceId", "InstanceId") if route.get(key)), None); target = route.get(target_key) if target_key else None
        routes.append({"destination_ipv4": _none_if_blank(route.get("DestinationCidrBlock")), "destination_ipv6": _none_if_blank(route.get("DestinationIpv6CidrBlock")), "target": target, "target_type": "internet_gateway" if target_key == "GatewayId" and str(target).startswith("igw-") else None})
    associations = [{"subnet_id": a.get("SubnetId")} for a in x.get("Associations", []) if a.get("SubnetId")]
    return ResourceSnapshot(ResourceIdentity("aws", "route_table", _name(tags, x["RouteTableId"])), ResourceCategory.NETWORKING, {"vpc_id": x.get("VpcId"), "routes": sorted(routes, key=repr), "associations": sorted(associations, key=repr), "tags": tags})


def _nacl(x: dict[str, Any]) -> ResourceSnapshot:
    tags = _tags(x.get("Tags", [])); entries = [{"egress": bool(e.get("Egress")), "rule_number": e.get("RuleNumber"), "protocol": str(e.get("Protocol")), "action": e.get("RuleAction"), "cidr_block": _none_if_blank(e.get("CidrBlock")), "ipv6_cidr_block": _none_if_blank(e.get("Ipv6CidrBlock"))} for e in x.get("Entries", []) if not _is_default_nacl_entry(e)]; associations = [{"subnet_id": a.get("SubnetId")} for a in x.get("Associations", [])]
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


def _is_default_nacl_entry(entry: dict[str, Any]) -> bool:
    return entry.get("RuleNumber") == 32767 and entry.get("RuleAction") == "deny"


def _none_if_blank(value: Any) -> Any:
    return None if value in (None, "") else value
