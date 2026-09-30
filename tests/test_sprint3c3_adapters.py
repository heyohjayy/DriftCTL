import copy

from driftctl.adapters.boto3_snapshots import adapt_boto3_inventory
from driftctl.adapters.terraform_state import adapt_terraform_state_with_diagnostics
from driftctl.detector import detect_drift
from driftctl.models import DriftType, Severity
from driftctl.presentation import (
    ImpactLevel,
    assess_impacts,
    explain_finding,
    readable_resource_type,
)
from driftctl.severity_rules import classify_finding, default_rules


CLUSTER_ARN = "arn:aws:eks:eu-west-1:123456789012:cluster/platform"
NODEGROUP_ARN = (
    "arn:aws:eks:eu-west-1:123456789012:nodegroup/platform/workers/nodegroup-id"
)
CLUSTER_ROLE = "arn:aws:iam::123456789012:role/eks-cluster"
NODE_ROLE = "arn:aws:iam::123456789012:role/eks-workers"
KMS_KEY = "arn:aws:kms:eu-west-1:123456789012:key/key-id"


def _state() -> dict:
    return {"values": {"root_module": {"resources": [
        {
            "address": "aws_eks_cluster.platform",
            "mode": "managed",
            "type": "aws_eks_cluster",
            "name": "platform",
            "values": {
                "name": "platform",
                "arn": CLUSTER_ARN,
                "version": "1.32",
                "role_arn": CLUSTER_ROLE,
                "vpc_config": [{
                    "subnet_ids": ["subnet-b", "subnet-a"],
                    "security_group_ids": ["sg-control"],
                    "endpoint_private_access": True,
                    "endpoint_public_access": False,
                    "public_access_cidrs": ["10.0.0.0/8"],
                }],
                "kubernetes_network_config": [{
                    "ip_family": "ipv4",
                    "service_ipv4_cidr": "172.20.0.0/16",
                    "service_ipv6_cidr": "",
                }],
                "enabled_cluster_log_types": ["audit", "api"],
                "encryption_config": [{
                    "resources": ["secrets"],
                    "provider": [{"key_arn": KMS_KEY}],
                }],
                "access_config": [{
                    "authentication_mode": "API_AND_CONFIG_MAP",
                    "bootstrap_cluster_creator_admin_permissions": False,
                }],
                "tags": {"Project": "Test"},
            },
        },
        {
            "address": "aws_eks_node_group.workers",
            "mode": "managed",
            "type": "aws_eks_node_group",
            "name": "workers",
            "values": {
                "cluster_name": "platform",
                "node_group_name": "workers",
                "node_group_arn": NODEGROUP_ARN,
                "node_role_arn": NODE_ROLE,
                "subnet_ids": ["subnet-b", "subnet-a"],
                "instance_types": ["t3.small"],
                "ami_type": "AL2023_x86_64_STANDARD",
                "capacity_type": "ON_DEMAND",
                "disk_size": 20,
                "version": "1.32",
                "scaling_config": [{"min_size": 1, "max_size": 3, "desired_size": 2}],
                "update_config": [{
                    "max_unavailable": 1,
                    "max_unavailable_percentage": None,
                }],
                "labels": {"workload": "general"},
                "taint": [{
                    "key": "dedicated",
                    "value": "general",
                    "effect": "NO_SCHEDULE",
                }],
                "remote_access": [],
                "launch_template": [],
                "tags": {"Project": "Test"},
            },
        },
    ]}}}


def _live() -> dict:
    return {
        "EKSClusters": [{
            "name": "platform",
            "arn": CLUSTER_ARN,
            "version": "1.32",
            "roleArn": CLUSTER_ROLE,
            "resourcesVpcConfig": {
                "subnetIds": ["subnet-a", "subnet-b"],
                "securityGroupIds": ["sg-control"],
                "endpointPrivateAccess": True,
                "endpointPublicAccess": False,
                "publicAccessCidrs": ["10.0.0.0/8"],
            },
            "kubernetesNetworkConfig": {
                "ipFamily": "ipv4",
                "serviceIpv4Cidr": "172.20.0.0/16",
            },
            "logging": {
                "clusterLogging": [{
                    "types": ["api", "audit"],
                    "enabled": True,
                }]
            },
            "encryptionConfig": [{
                "resources": ["secrets"],
                "provider": {"keyArn": KMS_KEY},
            }],
            "accessConfig": {
                "authenticationMode": "API_AND_CONFIG_MAP",
                "bootstrapClusterCreatorAdminPermissions": False,
            },
            "tags": {"Project": "Test"},
        }],
        "EKSNodegroups": [{
            "nodegroupName": "workers",
            "nodegroupArn": NODEGROUP_ARN,
            "clusterName": "platform",
            "version": "1.32",
            "nodeRole": NODE_ROLE,
            "subnets": ["subnet-a", "subnet-b"],
            "instanceTypes": ["t3.small"],
            "amiType": "AL2023_x86_64_STANDARD",
            "capacityType": "ON_DEMAND",
            "diskSize": 20,
            "scalingConfig": {"minSize": 1, "maxSize": 3, "desiredSize": 3},
            "updateConfig": {"maxUnavailable": 1},
            "labels": {"workload": "general"},
            "taints": [{
                "key": "dedicated",
                "value": "general",
                "effect": "NO_SCHEDULE",
            }],
            "tags": {"Project": "Test"},
        }],
    }


def test_matching_eks_cluster_and_node_group_have_no_drift() -> None:
    expected = adapt_terraform_state_with_diagnostics(_state())

    assert expected.diagnostics == ()
    assert detect_drift(expected.snapshots, adapt_boto3_inventory(_live())) == []
    assert {item.identity.resource_type for item in expected.snapshots} == {
        "eks_cluster",
        "eks_managed_node_group",
    }


def test_new_unrestricted_eks_public_endpoint_is_severe() -> None:
    live = _live()
    network = live["EKSClusters"][0]["resourcesVpcConfig"]
    network["endpointPublicAccess"] = True
    network["publicAccessCidrs"] = ["0.0.0.0/0"]
    finding = next(
        item
        for item in detect_drift(
            adapt_terraform_state_with_diagnostics(_state()).snapshots,
            adapt_boto3_inventory(live),
        )
        if item.identity.resource_type == "eks_cluster"
    )
    classify_finding(finding, default_rules())

    assert finding.drift_type is DriftType.MODIFIED
    assert set(finding.changes) == {"network"}
    assert finding.severity is Severity.SEVERE
    assert "EksPublicEndpointRule" in finding.severity_reason
    assert assess_impacts(finding).security is ImpactLevel.HIGH
    assert "unrestricted public CIDR" in explain_finding(finding).change
    assert readable_resource_type("eks_cluster") == "AWS EKS Cluster"


def test_eks_authentication_change_uses_control_plane_security_rule() -> None:
    live = _live()
    live["EKSClusters"][0]["accessConfig"]["authenticationMode"] = "CONFIG_MAP"
    finding = next(
        item
        for item in detect_drift(
            adapt_terraform_state_with_diagnostics(_state()).snapshots,
            adapt_boto3_inventory(live),
        )
        if item.identity.resource_type == "eks_cluster"
    )
    classify_finding(finding, default_rules())

    assert set(finding.changes) == {"access_config"}
    assert finding.severity is Severity.SEVERE
    assert "EksControlPlaneSecurityChangeRule" in finding.severity_reason


def test_node_group_scaling_and_label_changes_remain_modified() -> None:
    live = _live()
    live["EKSNodegroups"][0]["scalingConfig"]["maxSize"] = 4
    live["EKSNodegroups"][0]["labels"]["workload"] = "batch"
    finding = next(
        item
        for item in detect_drift(
            adapt_terraform_state_with_diagnostics(_state()).snapshots,
            adapt_boto3_inventory(live),
        )
        if item.identity.resource_type == "eks_managed_node_group"
    )

    assert finding.drift_type is DriftType.MODIFIED
    assert set(finding.changes) == {"labels", "scaling"}
    assert (
        readable_resource_type("eks_managed_node_group")
        == "AWS EKS Managed Node Group"
    )


def test_runtime_desired_size_difference_is_explicitly_ignored() -> None:
    live = _live()
    live["EKSNodegroups"][0]["scalingConfig"]["desiredSize"] = 1

    assert detect_drift(
        adapt_terraform_state_with_diagnostics(_state()).snapshots,
        adapt_boto3_inventory(live),
    ) == []


def test_in_scope_unmanaged_eks_resources_are_detected() -> None:
    live = _live()
    cluster = copy.deepcopy(live["EKSClusters"][0])
    cluster.update({
        "name": "console-cluster",
        "arn": "arn:aws:eks:eu-west-1:123456789012:cluster/console-cluster",
    })
    node_group = copy.deepcopy(live["EKSNodegroups"][0])
    node_group.update({
        "clusterName": "console-cluster",
        "nodegroupName": "console-workers",
    })
    live["EKSClusters"].append(cluster)
    live["EKSNodegroups"].append(node_group)

    findings = detect_drift(
        adapt_terraform_state_with_diagnostics(_state()).snapshots,
        adapt_boto3_inventory(live),
    )

    assert {
        item.identity.resource_type
        for item in findings
        if item.drift_type is DriftType.UNMANAGED
    } == {"eks_cluster", "eks_managed_node_group"}


def test_unsupported_eks_addon_remains_a_visible_diagnostic() -> None:
    state = _state()
    state["values"]["root_module"]["resources"].append({
        "address": "aws_eks_addon.coredns",
        "mode": "managed",
        "type": "aws_eks_addon",
        "name": "coredns",
        "values": {"cluster_name": "platform", "addon_name": "coredns"},
    })

    result = adapt_terraform_state_with_diagnostics(state)

    assert any(
        item.resource_address == "aws_eks_addon.coredns"
        and item.message == "Skipped unsupported Terraform resource type: aws_eks_addon."
        for item in result.diagnostics
    )
