"""Shared canonicalization for Terraform and boto3 EKS shapes."""

from __future__ import annotations

from typing import Any


def cluster_configuration(values: dict[str, Any]) -> dict[str, Any]:
    vpc = _first(values.get("vpc_config", values.get("resourcesVpcConfig")))
    network = _first(
        values.get("kubernetes_network_config", values.get("kubernetesNetworkConfig"))
    )
    access = _first(values.get("access_config", values.get("accessConfig")))
    return {
        "version": values.get("version"),
        "role_arn": values.get("role_arn", values.get("roleArn")),
        "network": {
            "subnet_ids": sorted(vpc.get("subnet_ids", vpc.get("subnetIds", []))),
            "security_group_ids": sorted(
                vpc.get("security_group_ids", vpc.get("securityGroupIds", []))
            ),
            "endpoint_private_access": bool(
                vpc.get(
                    "endpoint_private_access",
                    vpc.get("endpointPrivateAccess", False),
                )
            ),
            "endpoint_public_access": bool(
                vpc.get(
                    "endpoint_public_access",
                    vpc.get("endpointPublicAccess", True),
                )
            ),
            "public_access_cidrs": sorted(
                vpc.get(
                    "public_access_cidrs",
                    vpc.get("publicAccessCidrs", ["0.0.0.0/0"]),
                )
            ),
        },
        "kubernetes_network": {
            "ip_family": network.get("ip_family", network.get("ipFamily", "ipv4")),
            "service_ipv4_cidr": _none_if_blank(
                network.get("service_ipv4_cidr", network.get("serviceIpv4Cidr"))
            ),
            "service_ipv6_cidr": _none_if_blank(
                network.get("service_ipv6_cidr", network.get("serviceIpv6Cidr"))
            ),
        },
        "enabled_cluster_log_types": _enabled_log_types(values),
        "encryption_config": _encryption_config(
            values.get("encryption_config", values.get("encryptionConfig", []))
        ),
        "access_config": {
            "authentication_mode": access.get(
                "authentication_mode",
                access.get("authenticationMode", "CONFIG_MAP"),
            ),
            "bootstrap_cluster_creator_admin_permissions": bool(
                access.get(
                    "bootstrap_cluster_creator_admin_permissions",
                    access.get("bootstrapClusterCreatorAdminPermissions", True),
                )
            ),
        },
    }


def node_group_configuration(values: dict[str, Any]) -> dict[str, Any]:
    scaling = _first(values.get("scaling_config", values.get("scalingConfig")))
    update = _first(values.get("update_config", values.get("updateConfig")))
    remote = _first(values.get("remote_access", values.get("remoteAccess")))
    launch_template = _first(
        values.get("launch_template", values.get("launchTemplate"))
    )
    return {
        "cluster_name": values.get("cluster_name", values.get("clusterName")),
        "node_role_arn": values.get("node_role_arn", values.get("nodeRole")),
        "subnet_ids": sorted(values.get("subnet_ids", values.get("subnets", []))),
        "instance_types": sorted(
            values.get("instance_types", values.get("instanceTypes", []))
        ),
        "ami_type": values.get("ami_type", values.get("amiType")),
        "capacity_type": values.get(
            "capacity_type",
            values.get("capacityType", "ON_DEMAND"),
        ),
        "disk_size": values.get("disk_size", values.get("diskSize")),
        "version": values.get("version"),
        "scaling": {
            "min_size": scaling.get("min_size", scaling.get("minSize")),
            "max_size": scaling.get("max_size", scaling.get("maxSize")),
        },
        "update": {
            "max_unavailable": update.get(
                "max_unavailable",
                update.get("maxUnavailable"),
            ),
            "max_unavailable_percentage": update.get(
                "max_unavailable_percentage",
                update.get("maxUnavailablePercentage"),
            ),
        },
        "labels": dict(sorted((values.get("labels") or {}).items())),
        "taints": _taints(values.get("taint", values.get("taints", []))),
        "remote_access": {
            "ec2_ssh_key": _none_if_blank(
                remote.get("ec2_ssh_key", remote.get("ec2SshKey"))
            ),
            "source_security_group_ids": sorted(
                remote.get(
                    "source_security_group_ids",
                    remote.get("sourceSecurityGroups", []),
                )
            ),
        },
        "launch_template": {
            "id": _none_if_blank(launch_template.get("id")),
            "name": _none_if_blank(launch_template.get("name")),
        },
    }


def _enabled_log_types(values: dict[str, Any]) -> list[str]:
    terraform_types = values.get("enabled_cluster_log_types")
    if terraform_types is not None:
        return sorted(terraform_types)
    logging = values.get("logging") or {}
    return sorted({
        log_type
        for entry in logging.get("clusterLogging", [])
        if entry.get("enabled")
        for log_type in entry.get("types", [])
    })


def _encryption_config(values: Any) -> list[dict[str, Any]]:
    normalized = []
    for value in values or []:
        provider = _first(value.get("provider"))
        normalized.append({
            "resources": sorted(value.get("resources", [])),
            "key_arn": provider.get("key_arn", provider.get("keyArn")),
        })
    return sorted(normalized, key=repr)


def _taints(values: Any) -> list[dict[str, Any]]:
    return sorted(
        ({
            "key": value.get("key"),
            "value": _none_if_blank(value.get("value")),
            "effect": value.get("effect"),
        } for value in values or []),
        key=repr,
    )


def _first(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return value[0] if value else {}
    return value if isinstance(value, dict) else {}


def _none_if_blank(value: Any) -> Any:
    return None if value in (None, "") else value
