"""Translate terraform show -json-style state into normalized snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

from driftctl.adapters.security_group_rules import canonicalize_security_group_rules
from driftctl.models import CollectionDiagnostic, ResourceCategory, ResourceIdentity, ResourceSnapshot

_SUPPORTED = frozenset({
    "aws_security_group", "aws_vpc_security_group_ingress_rule", "aws_vpc_security_group_egress_rule",
    "aws_s3_bucket", "aws_s3_bucket_public_access_block", "aws_s3_bucket_server_side_encryption_configuration", "aws_instance",
    "aws_vpc", "aws_subnet", "aws_internet_gateway", "aws_route_table", "aws_route", "aws_route_table_association",
    "aws_network_acl", "aws_network_acl_rule", "aws_network_acl_association", "aws_iam_role", "aws_iam_role_policy_attachment",
    "aws_iam_role_policy", "aws_iam_instance_profile", "aws_route53_zone", "aws_route53_record",
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
    return ResourceSnapshot(ResourceIdentity("aws", "security_group", v.get("group_name") or r["name"]), ResourceCategory.NETWORKING, {"vpc_id": v.get("vpc_id"), "ingress": canonicalize_security_group_rules(ingress), "egress": canonicalize_security_group_rules(egress), "tags": v.get("tags", {})}, r.get("address"))


def _sg_rule(v: dict[str, Any]) -> dict[str, Any]:
    return {"from_port": v.get("from_port"), "to_port": v.get("to_port"), "protocol": v.get("ip_protocol", v.get("protocol")), "cidr_blocks": sorted((v.get("cidr_blocks") or []) + ([v["cidr_ipv4"]] if v.get("cidr_ipv4") else [])), "ipv6_cidr_blocks": sorted((v.get("ipv6_cidr_blocks") or []) + ([v["cidr_ipv6"]] if v.get("cidr_ipv6") else [])), "prefix_list_ids": sorted((v.get("prefix_list_ids") or []) + ([v["prefix_list_id"]] if v.get("prefix_list_id") else [])), "security_group_ids": sorted((v.get("security_groups") or []) + ([v["referenced_security_group_id"]] if v.get("referenced_security_group_id") else []))}


def _network(r: dict[str, Any], v: dict[str, Any], kind: str, attrs: dict[str, Any]) -> ResourceSnapshot: return ResourceSnapshot(ResourceIdentity("aws", kind, v.get("tags", {}).get("Name") or v.get("id") or r["name"]), ResourceCategory.NETWORKING, attrs, r.get("address"))

def _route_table(r: dict[str, Any], v: dict[str, Any], c: dict[str, Any]) -> ResourceSnapshot:
    routes = [_route(x) for x in v.get("route", [])] + c.get("routes", []); routes = [route for route in routes if route.get("target") != "local"]; return _network(r, v, "route_table", {"vpc_id": v.get("vpc_id"), "routes": sorted(routes, key=repr), "associations": sorted(c.get("associations", []), key=repr), "tags": v.get("tags", {})})

def _route(v: dict[str, Any]) -> dict[str, Any]:
    target = next((v.get(k) for k in ("gateway_id", "nat_gateway_id", "transit_gateway_id", "vpc_peering_connection_id", "network_interface_id", "instance_id") if v.get(k)), None); return {"destination_ipv4": v.get("destination_cidr_block") or v.get("cidr_block"), "destination_ipv6": v.get("destination_ipv6_cidr_block"), "target": target, "target_type": "internet_gateway" if target and str(target).startswith("igw-") else None}

def _nacl(r: dict[str, Any], v: dict[str, Any], c: dict[str, Any]) -> ResourceSnapshot:
    entries = [_acl_entry(x) for x in v.get("ingress", [])] + [_acl_entry({**x, "egress": True}) for x in v.get("egress", [])] + c.get("entries", []); return _network(r, v, "network_acl", {"vpc_id": v.get("vpc_id"), "entries": sorted(entries, key=repr), "associations": sorted(c.get("associations", []), key=repr), "tags": v.get("tags", {})})

def _acl_entry(v: dict[str, Any]) -> dict[str, Any]: return {"egress": bool(v.get("egress")), "rule_number": v.get("rule_no", v.get("rule_number")), "protocol": str(v.get("protocol")), "action": v.get("rule_action", v.get("action")), "cidr_block": v.get("cidr_block"), "ipv6_cidr_block": v.get("ipv6_cidr_block")}

def _role(r: dict[str, Any], v: dict[str, Any], c: dict[str, Any]) -> ResourceSnapshot:
    inline = [{"name": x.get("name"), "document": _json(x.get("policy"))} for x in v.get("inline_policy", [])] + c.get("inline", []); return ResourceSnapshot(ResourceIdentity("aws", "iam_role", v.get("name") or r["name"]), ResourceCategory.IAM, {"trust_policy": _json(v.get("assume_role_policy")), "managed_policy_arns": sorted(set((v.get("managed_policy_arns") or []) + [x for x in c.get("managed", []) if x])), "inline_policies": sorted(inline, key=repr), "tags": v.get("tags", {})}, r.get("address"))

def _profile(r: dict[str, Any], v: dict[str, Any]) -> ResourceSnapshot: return ResourceSnapshot(ResourceIdentity("aws", "iam_instance_profile", v.get("name") or r["name"]), ResourceCategory.IAM, {"roles": sorted([v["role"]] if v.get("role") else v.get("roles", [])), "tags": v.get("tags", {})}, r.get("address"))
def _zone(r: dict[str, Any], v: dict[str, Any]) -> ResourceSnapshot: return ResourceSnapshot(ResourceIdentity("aws", "route53_hosted_zone", _zone_name(v)), ResourceCategory.OTHER, {"private_zone": bool(v.get("private_zone")), "tags": v.get("tags", {})}, r.get("address"))
def _record(r: dict[str, Any], v: dict[str, Any], zone: str, tags: dict[str, str]) -> ResourceSnapshot:
    name, typ = str(v.get("name", "")).rstrip("."), v.get("type"); return ResourceSnapshot(ResourceIdentity("aws", "route53_record", f"{zone}|{name}|{typ}"), ResourceCategory.OTHER, {"zone": zone, "name": name, "type": typ, "ttl": v.get("ttl"), "records": sorted(v.get("records", [])), "alias": v.get("alias") or [], "tags": tags}, r.get("address"))
def _zone_name(v: dict[str, Any]) -> str: return str(v.get("name") or v.get("id") or "").rstrip(".")
def _json(value: Any) -> Any:
    if isinstance(value, str):
        try: return json.loads(value)
        except json.JSONDecodeError: return value
    return value or {}
def _s3(r: dict[str, Any], v: dict[str, Any], c: dict[str, Any]) -> ResourceSnapshot: return ResourceSnapshot(ResourceIdentity("aws", "s3_bucket", v.get("bucket") or r["name"]), ResourceCategory.STORAGE, {"bucket": v.get("bucket") or v.get("id"), "tags": v.get("tags", {}), "public_access_block": c.get("public_access_block", {}), "encryption": c.get("encryption", {})}, r.get("address"))
def _instance(r: dict[str, Any], v: dict[str, Any]) -> ResourceSnapshot: return ResourceSnapshot(ResourceIdentity("aws", "instance", v.get("tags", {}).get("Name") or v.get("id") or r["name"]), ResourceCategory.COMPUTE, {"instance_type": v.get("instance_type"), "ami": v.get("ami"), "subnet_id": v.get("subnet_id"), "associate_public_ip_address": bool(v.get("associate_public_ip_address")), "security_group_ids": sorted(v.get("vpc_security_group_ids", [])), "tags": v.get("tags", {})}, r.get("address"))
