"""Translate terraform show -json-style state into normalized snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from driftctl.adapters.ecs import (
    assign_public_ip,
    capacity_provider_strategy,
    cluster_settings,
    container_definitions,
    runtime_platform,
    task_definition_ref,
)
from driftctl.adapters.security_group_rules import canonicalize_security_group_rules
from driftctl.models import CollectionDiagnostic, ResourceCategory, ResourceIdentity, ResourceSnapshot

_SUPPORTED = frozenset({
    "aws_security_group", "aws_vpc_security_group_ingress_rule", "aws_vpc_security_group_egress_rule",
    "aws_s3_bucket", "aws_s3_bucket_public_access_block", "aws_s3_bucket_server_side_encryption_configuration", "aws_instance",
    "aws_vpc", "aws_subnet", "aws_internet_gateway", "aws_route_table", "aws_route", "aws_route_table_association",
    "aws_network_acl", "aws_network_acl_rule", "aws_network_acl_association", "aws_iam_role", "aws_iam_role_policy_attachment",
    "aws_iam_role_policy", "aws_iam_instance_profile", "aws_route53_zone", "aws_route53_record", "aws_nat_gateway",
    "aws_lb", "aws_alb", "aws_lb_target_group", "aws_lb_listener", "aws_lb_listener_rule", "aws_db_instance",
    "aws_ecs_cluster", "aws_ecs_task_definition", "aws_ecs_service", "aws_cloudwatch_log_group",
})


@dataclass(frozen=True)
class TerraformStateAdaptation:
    snapshots: list[ResourceSnapshot]
    diagnostics: tuple[CollectionDiagnostic, ...]


def adapt_terraform_state(payload: dict[str, Any]) -> list[ResourceSnapshot]:
    return adapt_terraform_state_with_diagnostics(payload).snapshots


def adapt_terraform_state_with_diagnostics(payload: dict[str, Any]) -> TerraformStateAdaptation:
    resources = list(_walk(payload.get("values", {}).get("root_module", {})))
    diagnostics = [CollectionDiagnostic("terraform_state", f"Skipped unsupported Terraform resource type: {r.get('type') or 'unknown'}.", r.get("address")) for r in resources if r.get("mode") == "managed" and r.get("type") not in _SUPPORTED]
    companions, child_diagnostics = _companions(resources)
    diagnostics.extend(child_diagnostics)
    zones = {v.get("zone_id") or v.get("id"): _zone_name(v) for r in resources if r.get("mode") == "managed" and r.get("type") == "aws_route53_zone" if (v := r.get("values", {}))}
    zone_tags = {v.get("zone_id") or v.get("id"): v.get("tags", {}) for r in resources if r.get("mode") == "managed" and r.get("type") == "aws_route53_zone" if (v := r.get("values", {}))}
    subnets = {v.get("id"): v.get("vpc_id") for r in resources if r.get("mode") == "managed" and r.get("type") == "aws_subnet" if (v := r.get("values", {}))}
    load_balancers = {v.get("arn"): _named(v, r) for r in resources if r.get("mode") == "managed" and r.get("type") in {"aws_lb", "aws_alb"} and _is_application_lb(v := r.get("values", {}))}
    load_balancer_tags = {v.get("arn"): v.get("tags", {}) for r in resources if r.get("mode") == "managed" and r.get("type") in {"aws_lb", "aws_alb"} and _is_application_lb(v := r.get("values", {}))}
    target_groups = {v.get("arn"): _named(v, r) for r in resources if r.get("mode") == "managed" and r.get("type") == "aws_lb_target_group" if (v := r.get("values", {}))}
    listeners = {v.get("arn"): _listener_name(v, load_balancers) for r in resources if r.get("mode") == "managed" and r.get("type") == "aws_lb_listener" if (v := r.get("values", {}))}
    listener_tags = {v.get("arn"): load_balancer_tags.get(v.get("load_balancer_arn"), {}) for r in resources if r.get("mode") == "managed" and r.get("type") == "aws_lb_listener" if (v := r.get("values", {}))}
    ecs_clusters, ecs_cluster_tags = _ecs_cluster_maps(resources)
    ecs_task_tags = _ecs_task_definition_tags(resources, ecs_cluster_tags)
    snapshots: list[ResourceSnapshot] = []
    for resource in resources:
        if resource.get("mode") != "managed":
            continue
        kind, values = resource.get("type"), resource.get("values", {})
        if kind == "aws_security_group": snapshots.append(_security_group(resource, values, companions["sg"].get(values.get("id"), {})))
        elif kind == "aws_s3_bucket": snapshots.append(_s3(resource, values, companions["bucket"].get(values.get("bucket") or values.get("id"), {})))
        elif kind == "aws_instance": snapshots.append(_instance(resource, values))
        elif kind == "aws_vpc": snapshots.append(_network(resource, values, "vpc", {"cidr_block": values.get("cidr_block"), "tags": values.get("tags", {})}))
        elif kind == "aws_subnet": snapshots.append(_network(resource, values, "subnet", {"vpc_id": values.get("vpc_id"), "cidr_block": values.get("cidr_block"), "availability_zone": values.get("availability_zone"), "map_public_ip_on_launch": bool(values.get("map_public_ip_on_launch")), "tags": values.get("tags", {})}))
        elif kind == "aws_internet_gateway": snapshots.append(_network(resource, values, "internet_gateway", {"vpc_id": values.get("vpc_id"), "tags": values.get("tags", {})}))
        elif kind == "aws_route_table": snapshots.append(_route_table(resource, values, companions["rt"].get(values.get("id"), {})))
        elif kind == "aws_network_acl": snapshots.append(_nacl(resource, values, companions["acl"].get(values.get("id"), {})))
        elif kind == "aws_iam_role": snapshots.append(_role(resource, values, companions["role"].get(values.get("name"), {})))
        elif kind == "aws_iam_instance_profile": snapshots.append(_profile(resource, values))
        elif kind == "aws_route53_zone": snapshots.append(_zone(resource, values))
        elif kind == "aws_nat_gateway": snapshots.append(_nat_gateway(resource, values, subnets))
        elif kind in {"aws_lb", "aws_alb"}:
            if _is_application_lb(values): snapshots.append(_load_balancer(resource, values))
            else: diagnostics.append(CollectionDiagnostic("terraform_state", "Skipped non-Application Load Balancer resource.", resource.get("address")))
        elif kind == "aws_lb_target_group": snapshots.append(_target_group(resource, values))
        elif kind == "aws_lb_listener": snapshots.append(_listener(resource, values, load_balancers, load_balancer_tags, target_groups))
        elif kind == "aws_lb_listener_rule":
            listener = listeners.get(values.get("listener_arn"))
            if listener: snapshots.append(_listener_rule(resource, values, listener, listener_tags.get(values.get("listener_arn"), {}), target_groups))
            else: diagnostics.append(CollectionDiagnostic("terraform_state", "Skipped listener rule because its parent listener is not supported in this state.", resource.get("address")))
        elif kind == "aws_db_instance": snapshots.append(_db_instance(resource, values))
        elif kind == "aws_ecs_cluster": snapshots.append(_ecs_cluster(resource, values))
        elif kind == "aws_ecs_task_definition": snapshots.append(_ecs_task_definition(resource, values, ecs_task_tags))
        elif kind == "aws_ecs_service": snapshots.append(_ecs_service(resource, values, ecs_clusters, ecs_cluster_tags, target_groups))
        elif kind == "aws_cloudwatch_log_group": snapshots.append(_log_group(resource, values))
        elif kind == "aws_route53_record":
            zone_id = values.get("zone_id")
            if zone_id not in zones: diagnostics.append(CollectionDiagnostic("terraform_state", "Skipped Route 53 record because its parent hosted zone is not supported in this state.", resource.get("address")))
            else: snapshots.append(_record(resource, values, zones[zone_id], zone_tags[zone_id]))
    return TerraformStateAdaptation(snapshots, tuple(diagnostics))


def _walk(module: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield from module.get("resources", [])
    for child in module.get("child_modules", []): yield from _walk(child)


def _companions(resources: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[CollectionDiagnostic]]:
    out = {"bucket": {}, "sg": {}, "rt": {}, "acl": {}, "role": {}}
    diagnostics: list[CollectionDiagnostic] = []
    parents = {
        "sg": {r.get("values", {}).get("id") for r in resources if r.get("mode") == "managed" and r.get("type") == "aws_security_group"},
        "rt": {r.get("values", {}).get("id") for r in resources if r.get("mode") == "managed" and r.get("type") == "aws_route_table"},
        "acl": {r.get("values", {}).get("id") for r in resources if r.get("mode") == "managed" and r.get("type") == "aws_network_acl"},
        "role": {r.get("values", {}).get("name") for r in resources if r.get("mode") == "managed" and r.get("type") == "aws_iam_role"},
    }
    for r in resources:
        if r.get("mode") != "managed": continue
        kind, v = r.get("type"), r.get("values", {})
        if kind == "aws_s3_bucket_public_access_block" and v.get("bucket"):
            out["bucket"].setdefault(v["bucket"], {})["public_access_block"] = {k: bool(v.get(k)) for k in ("block_public_acls", "ignore_public_acls", "block_public_policy", "restrict_public_buckets")}
        elif kind == "aws_s3_bucket_server_side_encryption_configuration" and v.get("bucket"):
            out["bucket"].setdefault(v["bucket"], {})["encryption"] = ((v.get("rule") or [{}])[0]).get("apply_server_side_encryption_by_default", {})
        elif kind in {"aws_vpc_security_group_ingress_rule", "aws_vpc_security_group_egress_rule"}:
            _attach(out["sg"], parents["sg"], v.get("security_group_id"), "ingress" if kind.endswith("ingress_rule") else "egress", _sg_rule(v), diagnostics, r, "security-group rule")
        elif kind in {"aws_route", "aws_route_table_association"}:
            pid = v.get("route_table_id"); child = "routes" if kind == "aws_route" else "associations"; value = _route(v) if kind == "aws_route" else {"subnet_id": v.get("subnet_id")}
            _attach(out["rt"], parents["rt"], pid, child, value, diagnostics, r, "route-table child")
        elif kind in {"aws_network_acl_rule", "aws_network_acl_association"}:
            pid = v.get("network_acl_id"); child = "entries" if kind == "aws_network_acl_rule" else "associations"; value = _acl_entry(v) if kind == "aws_network_acl_rule" else {"subnet_id": v.get("subnet_id")}
            _attach(out["acl"], parents["acl"], pid, child, value, diagnostics, r, "network-ACL child")
        elif kind in {"aws_iam_role_policy_attachment", "aws_iam_role_policy"}:
            role = v.get("role")
            if role not in parents["role"]: diagnostics.append(CollectionDiagnostic("terraform_state", "Skipped IAM role policy child because its parent role is not supported in this state.", r.get("address"))); continue
            parent = out["role"].setdefault(role, {"managed": [], "inline": []})
            (parent["managed"] if kind.endswith("attachment") else parent["inline"]).append(v.get("policy_arn") if kind.endswith("attachment") else {"name": v.get("name"), "document": _json(v.get("policy"))})
    return out, diagnostics


def _attach(store: dict[str, Any], parents: set[Any], parent: Any, child: str, value: Any, diagnostics: list[CollectionDiagnostic], resource: dict[str, Any], label: str) -> None:
    if parent not in parents: diagnostics.append(CollectionDiagnostic("terraform_state", f"Skipped {label} because its parent is not supported in this state.", resource.get("address"))); return
    store.setdefault(parent, {}).setdefault(child, []).append(value)


def _security_group(r: dict[str, Any], v: dict[str, Any], c: dict[str, Any]) -> ResourceSnapshot:
    ingress = [_sg_rule(x) for x in v.get("ingress", [])] + c.get("ingress", []); egress = [_sg_rule(x) for x in v.get("egress", [])] + c.get("egress", [])
    return ResourceSnapshot(ResourceIdentity("aws", "security_group", v.get("name") or v.get("group_name") or v.get("id") or r["name"]), ResourceCategory.NETWORKING, {"vpc_id": v.get("vpc_id"), "ingress": canonicalize_security_group_rules(ingress), "egress": canonicalize_security_group_rules(egress), "tags": v.get("tags", {})}, r.get("address"))


def _sg_rule(v: dict[str, Any]) -> dict[str, Any]:
    return {"from_port": v.get("from_port"), "to_port": v.get("to_port"), "protocol": v.get("ip_protocol", v.get("protocol")), "cidr_blocks": sorted((v.get("cidr_blocks") or []) + ([v["cidr_ipv4"]] if v.get("cidr_ipv4") else [])), "ipv6_cidr_blocks": sorted((v.get("ipv6_cidr_blocks") or []) + ([v["cidr_ipv6"]] if v.get("cidr_ipv6") else [])), "prefix_list_ids": sorted((v.get("prefix_list_ids") or []) + ([v["prefix_list_id"]] if v.get("prefix_list_id") else [])), "security_group_ids": sorted((v.get("security_groups") or []) + ([v["referenced_security_group_id"]] if v.get("referenced_security_group_id") else []))}


def _network(r: dict[str, Any], v: dict[str, Any], kind: str, attrs: dict[str, Any]) -> ResourceSnapshot: return ResourceSnapshot(ResourceIdentity("aws", kind, v.get("tags", {}).get("Name") or v.get("id") or r["name"]), ResourceCategory.NETWORKING, attrs, r.get("address"))

def _route_table(r: dict[str, Any], v: dict[str, Any], c: dict[str, Any]) -> ResourceSnapshot:
    routes = [_route(x) for x in v.get("route", [])] + c.get("routes", []); routes = _deduplicate([route for route in routes if route.get("target") != "local"]); return _network(r, v, "route_table", {"vpc_id": v.get("vpc_id"), "routes": sorted(routes, key=repr), "associations": sorted(c.get("associations", []), key=repr), "tags": v.get("tags", {})})

def _route(v: dict[str, Any]) -> dict[str, Any]:
    target = next((v.get(k) for k in ("gateway_id", "nat_gateway_id", "transit_gateway_id", "vpc_peering_connection_id", "network_interface_id", "instance_id") if v.get(k)), None); return {"destination_ipv4": _none_if_blank(v.get("destination_cidr_block") or v.get("cidr_block")), "destination_ipv6": _none_if_blank(v.get("destination_ipv6_cidr_block")), "target": target, "target_type": "internet_gateway" if target and str(target).startswith("igw-") else None}

def _nacl(r: dict[str, Any], v: dict[str, Any], c: dict[str, Any]) -> ResourceSnapshot:
    entries = [_acl_entry(x) for x in v.get("ingress", [])] + [_acl_entry({**x, "egress": True}) for x in v.get("egress", [])] + c.get("entries", []); return _network(r, v, "network_acl", {"vpc_id": v.get("vpc_id"), "entries": sorted(_deduplicate(entries), key=repr), "associations": sorted(c.get("associations", []), key=repr), "tags": v.get("tags", {})})

def _acl_entry(v: dict[str, Any]) -> dict[str, Any]: return {"egress": bool(v.get("egress")), "rule_number": v.get("rule_no", v.get("rule_number")), "protocol": str(v.get("protocol")), "action": v.get("rule_action", v.get("action")), "cidr_block": _none_if_blank(v.get("cidr_block")), "ipv6_cidr_block": _none_if_blank(v.get("ipv6_cidr_block"))}

def _role(r: dict[str, Any], v: dict[str, Any], c: dict[str, Any]) -> ResourceSnapshot:
    inline = [{"name": x.get("name"), "document": _json(x.get("policy"))} for x in v.get("inline_policy", [])] + c.get("inline", []); return ResourceSnapshot(ResourceIdentity("aws", "iam_role", v.get("name") or r["name"]), ResourceCategory.IAM, {"trust_policy": _json(v.get("assume_role_policy")), "managed_policy_arns": sorted(set((v.get("managed_policy_arns") or []) + [x for x in c.get("managed", []) if x])), "inline_policies": sorted(inline, key=repr), "tags": v.get("tags", {})}, r.get("address"))

def _profile(r: dict[str, Any], v: dict[str, Any]) -> ResourceSnapshot: return ResourceSnapshot(ResourceIdentity("aws", "iam_instance_profile", v.get("name") or r["name"]), ResourceCategory.IAM, {"roles": sorted([v["role"]] if v.get("role") else v.get("roles", [])), "tags": v.get("tags", {})}, r.get("address"))
def _zone(r: dict[str, Any], v: dict[str, Any]) -> ResourceSnapshot: return ResourceSnapshot(ResourceIdentity("aws", "route53_hosted_zone", _zone_name(v)), ResourceCategory.OTHER, {"private_zone": bool(v.get("private_zone")) or bool(v.get("vpc")), "tags": v.get("tags", {})}, r.get("address"))
def _record(r: dict[str, Any], v: dict[str, Any], zone: str, tags: dict[str, str]) -> ResourceSnapshot:
    name, typ = str(v.get("name", "")).rstrip("."), v.get("type"); return ResourceSnapshot(ResourceIdentity("aws", "route53_record", f"{zone}|{name}|{typ}"), ResourceCategory.OTHER, {"zone": zone, "name": name, "type": typ, "ttl": v.get("ttl"), "records": sorted(v.get("records", [])), "alias": v.get("alias") or [], "tags": tags}, r.get("address"))
def _zone_name(v: dict[str, Any]) -> str: return str(v.get("name") or v.get("id") or "").rstrip(".")
def _json(value: Any) -> Any:
    if isinstance(value, str):
        try: return json.loads(value)
        except json.JSONDecodeError: return value
    return value or {}
def _none_if_blank(value: Any) -> Any: return None if value in (None, "") else value
def _s3(r: dict[str, Any], v: dict[str, Any], c: dict[str, Any]) -> ResourceSnapshot: return ResourceSnapshot(ResourceIdentity("aws", "s3_bucket", v.get("bucket") or r["name"]), ResourceCategory.STORAGE, {"bucket": v.get("bucket") or v.get("id"), "tags": v.get("tags", {}), "public_access_block": c.get("public_access_block", {}), "encryption": c.get("encryption", {})}, r.get("address"))
def _instance(r: dict[str, Any], v: dict[str, Any]) -> ResourceSnapshot: return ResourceSnapshot(ResourceIdentity("aws", "instance", v.get("tags", {}).get("Name") or v.get("id") or r["name"]), ResourceCategory.COMPUTE, {"instance_type": v.get("instance_type"), "ami": v.get("ami"), "subnet_id": v.get("subnet_id"), "associate_public_ip_address": bool(v.get("associate_public_ip_address")), "security_group_ids": sorted(v.get("vpc_security_group_ids", [])), "tags": v.get("tags", {})}, r.get("address"))


def _ecs_cluster_maps(resources: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    names: dict[str, str] = {}
    tags: dict[str, dict[str, str]] = {}
    for resource in resources:
        if resource.get("mode") != "managed" or resource.get("type") != "aws_ecs_cluster":
            continue
        values = resource.get("values", {})
        name = values.get("name") or resource.get("name")
        for reference in (values.get("arn"), values.get("id"), name):
            if reference:
                names[str(reference)] = name
                tags[str(reference)] = values.get("tags", {})
    return names, tags


def _ecs_cluster(r: dict[str, Any], v: dict[str, Any]) -> ResourceSnapshot:
    name = v.get("name") or r["name"]
    return ResourceSnapshot(
        ResourceIdentity("aws", "ecs_cluster", name),
        ResourceCategory.COMPUTE,
        {"settings": cluster_settings(v.get("setting")), "tags": v.get("tags", {})},
        r.get("address"),
    )


def _ecs_task_definition_tags(resources: list[dict[str, Any]], cluster_tags: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    tags: dict[str, dict[str, str]] = {}
    for resource in resources:
        if resource.get("mode") != "managed" or resource.get("type") != "aws_ecs_service":
            continue
        values = resource.get("values", {})
        reference = task_definition_ref(values.get("task_definition"))
        if reference:
            cluster_ref = str(values.get("cluster") or "default")
            tags[reference] = values.get("tags", {}) or cluster_tags.get(cluster_ref, {})
    return tags


def _ecs_task_definition(r: dict[str, Any], v: dict[str, Any], inherited_tags: dict[str, dict[str, str]]) -> ResourceSnapshot:
    identity = task_definition_ref(v.get("arn")) or f"{v.get('family') or r['name']}:{v.get('revision')}"
    ephemeral = _first(v.get("ephemeral_storage"))
    return ResourceSnapshot(
        ResourceIdentity("aws", "ecs_task_definition", identity),
        ResourceCategory.COMPUTE,
        {
            "family": v.get("family") or r["name"],
            "revision": v.get("revision"),
            "network_mode": v.get("network_mode"),
            "requires_compatibilities": sorted(v.get("requires_compatibilities", [])),
            "cpu": _string_or_none(v.get("cpu")),
            "memory": _string_or_none(v.get("memory")),
            "execution_role_arn": v.get("execution_role_arn"),
            "task_role_arn": v.get("task_role_arn"),
            "runtime_platform": runtime_platform(v.get("runtime_platform")),
            "ephemeral_storage_gib": ephemeral.get("size_in_gib"),
            "container_definitions": container_definitions(v.get("container_definitions")),
            "tags": v.get("tags", {}) or inherited_tags.get(identity, {}),
        },
        r.get("address"),
    )


def _ecs_service(
    r: dict[str, Any],
    v: dict[str, Any],
    clusters: dict[str, str],
    cluster_tags: dict[str, dict[str, str]],
    target_groups: dict[str, str],
) -> ResourceSnapshot:
    cluster_ref = str(v.get("cluster") or "default")
    cluster = clusters.get(cluster_ref, cluster_ref.rsplit("/", 1)[-1])
    network = _first(v.get("network_configuration"))
    deployment = _first(v.get("deployment_circuit_breaker"))
    tags = v.get("tags", {}) or cluster_tags.get(cluster_ref, {})
    return ResourceSnapshot(
        ResourceIdentity("aws", "ecs_service", f"{cluster}|{v.get('name') or r['name']}"),
        ResourceCategory.COMPUTE,
        {
            "cluster": cluster,
            "task_definition": task_definition_ref(v.get("task_definition")),
            "desired_count": v.get("desired_count"),
            "launch_type": v.get("launch_type"),
            "capacity_provider_strategy": capacity_provider_strategy(v.get("capacity_provider_strategy")),
            "network_configuration": {
                "subnets": sorted(network.get("subnets", [])),
                "security_groups": sorted(network.get("security_groups", [])),
                "assign_public_ip": assign_public_ip(network.get("assign_public_ip")),
            },
            "deployment": {
                "minimum_healthy_percent": v.get("deployment_minimum_healthy_percent", 100),
                "maximum_percent": v.get("deployment_maximum_percent", 200),
                "circuit_breaker_enable": deployment.get("enable", False),
                "circuit_breaker_rollback": deployment.get("rollback", False),
            },
            "scheduling_strategy": v.get("scheduling_strategy") or "REPLICA",
            "enable_execute_command": bool(v.get("enable_execute_command")),
            "load_balancers": _ecs_load_balancers(v.get("load_balancer", []), target_groups),
            "tags": tags,
        },
        r.get("address"),
    )


def _ecs_load_balancers(values: list[dict[str, Any]], target_groups: dict[str, str]) -> list[dict[str, Any]]:
    return sorted(
        ({
            "target_group": target_groups.get(item.get("target_group_arn"), item.get("target_group_arn")),
            "container_name": item.get("container_name"),
            "container_port": item.get("container_port"),
        } for item in values),
        key=repr,
    )


def _log_group(r: dict[str, Any], v: dict[str, Any]) -> ResourceSnapshot:
    return ResourceSnapshot(
        ResourceIdentity("aws", "cloudwatch_log_group", v.get("name") or r["name"]),
        ResourceCategory.OTHER,
        {
            "retention_in_days": v.get("retention_in_days"),
            "kms_key_id": v.get("kms_key_id"),
            "log_group_class": v.get("log_group_class") or "STANDARD",
            "tags": v.get("tags", {}),
        },
        r.get("address"),
    )


def _first(value: Any) -> dict[str, Any]:
    if isinstance(value, list): return value[0] if value else {}
    return value if isinstance(value, dict) else {}


def _string_or_none(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _named(v: dict[str, Any], r: dict[str, Any]) -> str: return v.get("tags", {}).get("Name") or v.get("name") or v.get("id") or r["name"]
def _is_application_lb(v: dict[str, Any]) -> bool: return v.get("load_balancer_type", "application") == "application"
def _nat_gateway(r: dict[str, Any], v: dict[str, Any], subnets: dict[str, Any]) -> ResourceSnapshot:
    subnet = v.get("subnet_id"); return ResourceSnapshot(ResourceIdentity("aws", "nat_gateway", _named(v, r)), ResourceCategory.NETWORKING, {"subnet_id": subnet, "vpc_id": v.get("vpc_id") or subnets.get(subnet), "allocation_ids": sorted([v["allocation_id"]] if v.get("allocation_id") else []), "connectivity_type": v.get("connectivity_type") or "public", "state": v.get("state") or "available", "tags": v.get("tags", {})}, r.get("address"))
def _load_balancer(r: dict[str, Any], v: dict[str, Any]) -> ResourceSnapshot:
    subnet_ids = list(v.get("subnets", [])) + [item.get("subnet_id") for item in v.get("subnet_mapping", []) if item.get("subnet_id")]
    return ResourceSnapshot(ResourceIdentity("aws", "application_load_balancer", _named(v, r)), ResourceCategory.NETWORKING, {"scheme": v.get("internal") and "internal" or "internet-facing", "ip_address_type": v.get("ip_address_type") or "ipv4", "subnet_ids": sorted(set(subnet_ids)), "security_group_ids": sorted(v.get("security_groups", [])), "tags": v.get("tags", {})}, r.get("address"))
def _target_group(r: dict[str, Any], v: dict[str, Any]) -> ResourceSnapshot:
    health = v.get("health_check", [{}]); health = health[0] if isinstance(health, list) and health else {}; return ResourceSnapshot(ResourceIdentity("aws", "target_group", _named(v, r)), ResourceCategory.NETWORKING, {"vpc_id": v.get("vpc_id"), "protocol": v.get("protocol"), "port": v.get("port"), "target_type": v.get("target_type") or "instance", "health_check": _health_check(health), "tags": v.get("tags", {})}, r.get("address"))
def _listener_name(v: dict[str, Any], load_balancers: dict[str, str]) -> str:
    return f"{load_balancers.get(v.get('load_balancer_arn'), v.get('load_balancer_arn', 'unknown'))}|{v.get('protocol')}|{v.get('port')}"
def _listener(r: dict[str, Any], v: dict[str, Any], load_balancers: dict[str, str], load_balancer_tags: dict[str, dict[str, str]], target_groups: dict[str, str]) -> ResourceSnapshot:
    lb_arn = v.get("load_balancer_arn"); lb_name = load_balancers.get(lb_arn, lb_arn or "unknown"); return ResourceSnapshot(ResourceIdentity("aws", "load_balancer_listener", f"{lb_name}|{v.get('protocol')}|{v.get('port')}"), ResourceCategory.NETWORKING, {"load_balancer": lb_name, "protocol": v.get("protocol"), "port": v.get("port"), "ssl_policy": _none_if_blank(v.get("ssl_policy")), "certificate_arn": _none_if_blank(v.get("certificate_arn")), "default_actions": _actions(v.get("default_action", []), target_groups), "tags": v.get("tags", {}) or load_balancer_tags.get(lb_arn, {})}, r.get("address"))
def _listener_rule(r: dict[str, Any], v: dict[str, Any], listener: str, inherited_tags: dict[str, str], target_groups: dict[str, str]) -> ResourceSnapshot:
    return ResourceSnapshot(ResourceIdentity("aws", "load_balancer_listener_rule", f"{listener}|{v.get('priority')}"), ResourceCategory.NETWORKING, {"listener": listener, "priority": str(v.get("priority")), "conditions": _conditions(v.get("condition", [])), "actions": _actions(v.get("action", []), target_groups), "tags": v.get("tags", {}) or inherited_tags}, r.get("address"))
def _db_instance(r: dict[str, Any], v: dict[str, Any]) -> ResourceSnapshot:
    return ResourceSnapshot(ResourceIdentity("aws", "rds_db_instance", _named(v, r)), ResourceCategory.DATABASE, {"engine": v.get("engine"), "engine_version": v.get("engine_version"), "instance_class": v.get("instance_class"), "allocated_storage": v.get("allocated_storage"), "storage_type": v.get("storage_type"), "storage_encrypted": bool(v.get("storage_encrypted")), "publicly_accessible": bool(v.get("publicly_accessible")), "vpc_security_group_ids": sorted(v.get("vpc_security_group_ids", [])), "db_subnet_group_name": v.get("db_subnet_group_name"), "backup_retention_period": v.get("backup_retention_period"), "deletion_protection": bool(v.get("deletion_protection")), "multi_az": bool(v.get("multi_az")), "port": v.get("port"), "copy_tags_to_snapshot": bool(v.get("copy_tags_to_snapshot")), "tags": v.get("tags", {})}, r.get("address"))
def _health_check(v: dict[str, Any]) -> dict[str, Any]: return {"enabled": bool(v.get("enabled", True)), "protocol": v.get("protocol"), "port": v.get("port"), "path": v.get("path"), "interval": v.get("interval"), "timeout": v.get("timeout"), "healthy_threshold": v.get("healthy_threshold"), "unhealthy_threshold": v.get("unhealthy_threshold"), "matcher": v.get("matcher")}
def _actions(actions: list[dict[str, Any]], target_groups: dict[str, str]) -> list[dict[str, Any]]:
    return sorted([{"type": action.get("type"), "target_groups": _forward_tf(action, target_groups), "redirect": _redirect_tf(action.get("redirect")), "fixed_response": _fixed_response_tf(action.get("fixed_response"))} for action in actions], key=repr)
def _conditions(conditions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values = []
    for item in conditions:
        host = (item.get("host_header") or [{}])[0]; path = (item.get("path_pattern") or [{}])[0]
        field = "host-header" if item.get("host_header") else "path-pattern" if item.get("path_pattern") else item.get("field")
        values.append({"field": field, "values": sorted(item.get("values") or host.get("values") or path.get("values") or [])})
    return sorted(values, key=repr)
def _redirect_tf(value: Any) -> list[dict[str, Any]]:
    if not value: return []
    item = value[0] if isinstance(value, list) else value; return [{"protocol": item.get("protocol"), "host": item.get("host"), "port": item.get("port"), "path": item.get("path"), "query": item.get("query"), "status_code": item.get("status_code")}]
def _fixed_response_tf(value: Any) -> list[dict[str, Any]]:
    if not value: return []
    item = value[0] if isinstance(value, list) else value; return [{"content_type": item.get("content_type"), "message_body": item.get("message_body"), "status_code": item.get("status_code")}]
def _forward_tf(action: dict[str, Any], target_groups: dict[str, str]) -> list[dict[str, Any]]:
    values = []
    for forward in action.get("forward") or []:
        for target in forward.get("target_group") or []:
            arn = target.get("arn"); values.append({"target_group": target_groups.get(arn, arn), "weight": target.get("weight")})
    if not values and action.get("target_group_arn"): values.append({"target_group": target_groups.get(action["target_group_arn"], action["target_group_arn"]), "weight": None})
    return sorted(values, key=repr)
def _deduplicate(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list({json.dumps(value, default=str, sort_keys=True): value for value in values}.values())
