from datetime import datetime, timezone

import boto3
from botocore.stub import Stubber

from driftctl.collectors.aws import AwsInventoryCollector


def _session() -> boto3.Session:
    return boto3.Session(
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="eu-west-1",
    )


def _cluster(name: str, project: str) -> dict:
    return {
        "name": name,
        "arn": f"arn:aws:eks:eu-west-1:123456789012:cluster/{name}",
        "createdAt": datetime(2026, 9, 30, tzinfo=timezone.utc),
        "version": "1.32",
        "endpoint": f"https://{name}.eks.example",
        "roleArn": "arn:aws:iam::123456789012:role/eks-cluster",
        "resourcesVpcConfig": {
            "subnetIds": ["subnet-a", "subnet-b"],
            "securityGroupIds": ["sg-control"],
            "clusterSecurityGroupId": "sg-generated",
            "vpcId": "vpc-1",
            "endpointPublicAccess": False,
            "endpointPrivateAccess": True,
            "publicAccessCidrs": ["10.0.0.0/8"],
        },
        "kubernetesNetworkConfig": {
            "serviceIpv4Cidr": "172.20.0.0/16",
            "ipFamily": "ipv4",
        },
        "logging": {"clusterLogging": []},
        "identity": {"oidc": {"issuer": f"https://oidc.eks/{name}"}},
        "status": "ACTIVE",
        "certificateAuthority": {"data": "certificate"},
        "platformVersion": "eks.1",
        "tags": {"Project": project},
        "accessConfig": {
            "authenticationMode": "API_AND_CONFIG_MAP",
            "bootstrapClusterCreatorAdminPermissions": False,
        },
    }


def _node_group(cluster: str, name: str, tags: dict[str, str]) -> dict:
    now = datetime(2026, 9, 30, tzinfo=timezone.utc)
    return {
        "nodegroupName": name,
        "nodegroupArn": (
            f"arn:aws:eks:eu-west-1:123456789012:nodegroup/{cluster}/{name}/id"
        ),
        "clusterName": cluster,
        "version": "1.32",
        "releaseVersion": "1.32.0-20260901",
        "createdAt": now,
        "modifiedAt": now,
        "status": "ACTIVE",
        "capacityType": "ON_DEMAND",
        "scalingConfig": {"minSize": 1, "maxSize": 2, "desiredSize": 1},
        "instanceTypes": ["t3.small"],
        "subnets": ["subnet-a", "subnet-b"],
        "amiType": "AL2023_x86_64_STANDARD",
        "nodeRole": "arn:aws:iam::123456789012:role/eks-workers",
        "labels": {},
        "taints": [],
        "resources": {"autoScalingGroups": [{"name": f"{cluster}-{name}"}]},
        "diskSize": 20,
        "health": {"issues": []},
        "updateConfig": {"maxUnavailable": 1},
        "tags": tags,
    }


def test_eks_collection_filters_clusters_and_inherits_scope_to_node_groups() -> None:
    client = _session().client("eks")
    stubber = Stubber(client)
    in_cluster = _cluster("in-cluster", "Test")
    out_cluster = _cluster("out-cluster", "Other")
    worker = _node_group("in-cluster", "workers", {})

    stubber.add_response(
        "list_clusters",
        {"clusters": ["in-cluster", "out-cluster"]},
    )
    stubber.add_response(
        "describe_cluster",
        {"cluster": in_cluster},
        {"name": "in-cluster"},
    )
    stubber.add_response(
        "describe_cluster",
        {"cluster": out_cluster},
        {"name": "out-cluster"},
    )
    stubber.add_response(
        "list_nodegroups",
        {"nodegroups": ["workers"]},
        {"clusterName": "in-cluster"},
    )
    stubber.add_response(
        "describe_nodegroup",
        {"nodegroup": worker},
        {"clusterName": "in-cluster", "nodegroupName": "workers"},
    )
    stubber.add_response(
        "list_nodegroups",
        {"nodegroups": []},
        {"clusterName": "out-cluster"},
    )

    with stubber:
        inventory = AwsInventoryCollector(
            None,
            None,
            eks_client=client,
        )._eks_inventory({"Project": "Test"})

    assert [item["name"] for item in inventory["EKSClusters"]] == ["in-cluster"]
    assert [item["nodegroupName"] for item in inventory["EKSNodegroups"]] == [
        "workers"
    ]
    assert inventory["EKSNodegroups"][0]["tags"] == {"Project": "Test"}
