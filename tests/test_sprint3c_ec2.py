import copy
import json

from driftctl.adapters.boto3_snapshots import adapt_boto3_inventory
from driftctl.adapters.terraform_state import adapt_terraform_state_with_diagnostics
from driftctl.detector import detect_drift
from driftctl.models import DriftType
from driftctl.presentation import readable_resource_type


CLUSTER_ARN = "arn:aws:ecs:eu-west-1:123456789012:cluster/platform"
TASK_ARN = "arn:aws:ecs:eu-west-1:123456789012:task-definition/worker:1"
ASG_ARN = "arn:aws:autoscaling:eu-west-1:123456789012:autoScalingGroup:asg-id:autoScalingGroupName/ecs-workers"


def _state() -> dict:
    containers = [{
        "name": "worker",
        "image": "123456789012.dkr.ecr.eu-west-1.amazonaws.com/worker:1",
        "cpu": 128,
        "essential": True,
        "privileged": True,
        "resourceRequirements": [{"type": "GPU", "value": "1"}],
    }]
    return {"values": {"root_module": {"resources": [
        {"address": "aws_ecs_cluster.platform", "mode": "managed", "type": "aws_ecs_cluster", "name": "platform", "values": {"arn": CLUSTER_ARN, "id": CLUSTER_ARN, "name": "platform", "setting": [], "tags": {"Project": "Test"}}},
        {"address": "aws_ecs_cluster_capacity_providers.platform", "mode": "managed", "type": "aws_ecs_cluster_capacity_providers", "name": "platform", "values": {"cluster_name": "platform", "capacity_providers": ["platform-ec2"], "default_capacity_provider_strategy": [{"capacity_provider": "platform-ec2", "weight": 1, "base": 0}]}},
        {"address": "aws_ecs_capacity_provider.platform", "mode": "managed", "type": "aws_ecs_capacity_provider", "name": "platform", "values": {"name": "platform-ec2", "auto_scaling_group_provider": [{"auto_scaling_group_arn": ASG_ARN, "managed_draining": "ENABLED", "managed_termination_protection": "ENABLED", "managed_scaling": [{"status": "ENABLED", "target_capacity": 80, "minimum_scaling_step_size": 1, "maximum_scaling_step_size": 4}]}], "tags": {"Project": "Test"}}},
        {"address": "aws_ecs_task_definition.worker", "mode": "managed", "type": "aws_ecs_task_definition", "name": "worker", "values": {"arn": TASK_ARN, "family": "worker", "revision": 1, "network_mode": "bridge", "requires_compatibilities": ["EC2"], "cpu": None, "memory": None, "execution_role_arn": None, "task_role_arn": None, "ipc_mode": "host", "pid_mode": "host", "placement_constraints": [{"type": "memberOf", "expression": "attribute:ecs.instance-type =~ t3.*"}], "container_definitions": json.dumps(containers), "tags": {"Project": "Test"}}},
        {"address": "aws_ecs_service.worker", "mode": "managed", "type": "aws_ecs_service", "name": "worker", "values": {"name": "worker", "cluster": CLUSTER_ARN, "task_definition": TASK_ARN, "desired_count": 2, "launch_type": None, "capacity_provider_strategy": [{"capacity_provider": "platform-ec2", "weight": 1, "base": 0}], "placement_constraints": [{"type": "memberOf", "expression": "attribute:ecs.instance-type =~ t3.*"}], "ordered_placement_strategy": [{"type": "spread", "field": "attribute:ecs.availability-zone"}, {"type": "binpack", "field": "memory"}], "network_configuration": [], "deployment_circuit_breaker": [], "tags": {"Project": "Test"}}},
    ]}}}


def _live() -> dict:
    return {
        "ECSClusters": [{"clusterArn": CLUSTER_ARN, "clusterName": "platform", "settings": [], "capacityProviders": ["FARGATE", "platform-ec2"], "defaultCapacityProviderStrategy": [{"capacityProvider": "FARGATE", "weight": 0, "base": 0}, {"capacityProvider": "platform-ec2", "weight": 1, "base": 0}], "tags": [{"key": "Project", "value": "Test"}]}],
        "ECSCapacityProviders": [{"name": "platform-ec2", "status": "ACTIVE", "autoScalingGroupProvider": {"autoScalingGroupArn": ASG_ARN, "managedDraining": "ENABLED", "managedTerminationProtection": "ENABLED", "managedScaling": {"status": "ENABLED", "targetCapacity": 80, "minimumScalingStepSize": 1, "maximumScalingStepSize": 4}}, "tags": [{"key": "Project", "value": "Test"}]}],
        "ECSTaskDefinitions": [{"taskDefinitionArn": TASK_ARN, "family": "worker", "revision": 1, "networkMode": "bridge", "requiresCompatibilities": ["EC2"], "ipcMode": "host", "pidMode": "host", "placementConstraints": [{"type": "memberOf", "expression": "attribute:ecs.instance-type =~ t3.*"}], "containerDefinitions": [{"name": "worker", "image": "123456789012.dkr.ecr.eu-west-1.amazonaws.com/worker:1", "cpu": 128, "essential": True, "privileged": True, "resourceRequirements": [{"type": "GPU", "value": "1"}]}], "tags": [{"key": "Project", "value": "Test"}]}],
        "ECSServices": [{"serviceName": "worker", "clusterArn": CLUSTER_ARN, "taskDefinition": TASK_ARN, "desiredCount": 2, "capacityProviderStrategy": [{"capacityProvider": "platform-ec2", "weight": 1, "base": 0}], "placementConstraints": [{"type": "memberOf", "expression": "attribute:ecs.instance-type =~ t3.*"}], "placementStrategy": [{"type": "spread", "field": "attribute:ecs.availability-zone"}, {"type": "binpack", "field": "memory"}], "deploymentConfiguration": {}, "networkConfiguration": {}, "tags": [{"key": "Project", "value": "Test"}]}],
    }


def test_matching_ecs_on_ec2_capacity_and_placement_inventory_has_no_drift() -> None:
    expected = adapt_terraform_state_with_diagnostics(_state())
    live = adapt_boto3_inventory(_live())

    assert expected.diagnostics == ()
    assert detect_drift(expected.snapshots, live) == []
    assert {item.identity.resource_type for item in expected.snapshots} == {
        "ecs_cluster",
        "ecs_capacity_provider",
        "ecs_task_definition",
        "ecs_service",
    }
    assert readable_resource_type("ecs_capacity_provider") == "AWS ECS Capacity Provider"


def test_ecs_on_ec2_capacity_and_placement_changes_are_modified() -> None:
    live = _live()
    live["ECSCapacityProviders"][0]["autoScalingGroupProvider"]["managedScaling"]["targetCapacity"] = 60
    live["ECSServices"][0]["placementStrategy"][1]["field"] = "cpu"

    findings = detect_drift(
        adapt_terraform_state_with_diagnostics(_state()).snapshots,
        adapt_boto3_inventory(live),
    )
    by_type = {finding.identity.resource_type: finding for finding in findings}

    assert by_type["ecs_capacity_provider"].drift_type is DriftType.MODIFIED
    assert set(by_type["ecs_capacity_provider"].changes) == {"auto_scaling_group_provider"}
    assert by_type["ecs_service"].drift_type is DriftType.MODIFIED
    assert set(by_type["ecs_service"].changes) == {"placement_strategy"}


def test_aws_managed_fargate_cluster_capacity_defaults_do_not_create_drift() -> None:
    state = copy.deepcopy(_state())
    resources = state["values"]["root_module"]["resources"]
    resources[:] = [resource for resource in resources if resource["type"] == "aws_ecs_cluster"]
    live = {
        "ECSClusters": [{
            "clusterArn": CLUSTER_ARN,
            "clusterName": "platform",
            "settings": [],
            "capacityProviders": ["FARGATE", "FARGATE_SPOT"],
            "defaultCapacityProviderStrategy": [{"capacityProvider": "FARGATE", "weight": 1, "base": 0}],
            "tags": [{"key": "Project", "value": "Test"}],
        }],
    }

    assert detect_drift(
        adapt_terraform_state_with_diagnostics(state).snapshots,
        adapt_boto3_inventory(live),
    ) == []
