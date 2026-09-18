import boto3
from botocore.stub import Stubber

from driftctl.adapters.boto3_snapshots import adapt_boto3_inventory
from driftctl.adapters.terraform_state import adapt_terraform_state_with_diagnostics
from driftctl.collectors.aws import AwsInventoryCollector
from driftctl.detector import detect_drift


def _session() -> boto3.Session:
    return boto3.Session(aws_access_key_id="testing", aws_secret_access_key="testing", region_name="eu-west-1")


def test_ecs_collection_paginates_and_applies_direct_and_inherited_tag_scope() -> None:
    ecs = _session().client("ecs")
    stubber = Stubber(ecs)
    cluster_in = "arn:aws:ecs:eu-west-1:123456789012:cluster/in"
    cluster_out = "arn:aws:ecs:eu-west-1:123456789012:cluster/out"
    service = "arn:aws:ecs:eu-west-1:123456789012:service/in/console-service"
    task = "arn:aws:ecs:eu-west-1:123456789012:task-definition/web:1"
    scope_tags = [{"key": "Project", "value": "Test"}]

    stubber.add_response("list_clusters", {"clusterArns": [cluster_in], "nextToken": "next"})
    stubber.add_response("list_clusters", {"clusterArns": [cluster_out]}, {"nextToken": "next"})
    stubber.add_response(
        "describe_clusters",
        {"clusters": [
            {"clusterArn": cluster_in, "clusterName": "in", "status": "ACTIVE", "registeredContainerInstancesCount": 0, "runningTasksCount": 0, "pendingTasksCount": 0, "activeServicesCount": 1, "statistics": [], "tags": scope_tags, "settings": []},
            {"clusterArn": cluster_out, "clusterName": "out", "status": "ACTIVE", "registeredContainerInstancesCount": 0, "runningTasksCount": 0, "pendingTasksCount": 0, "activeServicesCount": 0, "statistics": [], "tags": [{"key": "Project", "value": "Other"}], "settings": []},
        ]},
        {"clusters": [cluster_in, cluster_out], "include": ["TAGS", "SETTINGS"]},
    )
    stubber.add_response("list_services", {"serviceArns": [service], "nextToken": "services-next"}, {"cluster": cluster_in})
    stubber.add_response("list_services", {"serviceArns": []}, {"cluster": cluster_in, "nextToken": "services-next"})
    stubber.add_response(
        "describe_services",
        {"services": [{"serviceArn": service, "serviceName": "console-service", "clusterArn": cluster_in, "taskDefinition": task, "desiredCount": 1, "runningCount": 1, "pendingCount": 0, "launchType": "FARGATE", "platformVersion": "1.4.0", "platformFamily": "Linux", "deploymentConfiguration": {}, "deployments": [], "roleArn": "arn:aws:iam::123456789012:role/aws-service-role/ecs", "events": [], "createdAt": 0.0, "placementConstraints": [], "placementStrategy": [], "networkConfiguration": {}, "healthCheckGracePeriodSeconds": 0, "schedulingStrategy": "REPLICA", "deploymentController": {"type": "ECS"}, "createdBy": "arn:aws:iam::123456789012:user/test", "enableECSManagedTags": False, "propagateTags": "NONE", "enableExecuteCommand": False, "tags": []}]},
        {"cluster": cluster_in, "services": [service], "include": ["TAGS"]},
    )
    stubber.add_response("list_services", {"serviceArns": []}, {"cluster": cluster_out})
    stubber.add_response("list_task_definitions", {"taskDefinitionArns": [task]}, {"status": "ACTIVE"})
    stubber.add_response(
        "describe_task_definition",
        {"taskDefinition": {"taskDefinitionArn": task, "containerDefinitions": [], "family": "web", "revision": 1, "networkMode": "awsvpc", "status": "ACTIVE", "requiresAttributes": [], "compatibilities": ["EC2", "FARGATE"], "requiresCompatibilities": ["FARGATE"], "cpu": "256", "memory": "512"}, "tags": []},
        {"taskDefinition": task, "include": ["TAGS"]},
    )
    stubber.add_response("describe_capacity_providers", {"capacityProviders": []}, {"include": ["TAGS"]})

    with stubber:
        inventory = AwsInventoryCollector(None, None, ecs_client=ecs)._ecs({"Project": "Test"})

    assert [item["clusterName"] for item in inventory["ECSClusters"]] == ["in"]
    assert [item["serviceName"] for item in inventory["ECSServices"]] == ["console-service"]
    assert inventory["ECSServices"][0]["tags"] == scope_tags
    assert [item["family"] for item in inventory["ECSTaskDefinitions"]] == ["web"]
    assert inventory["ECSTaskDefinitions"][0]["tags"] == scope_tags


def test_ecs_collection_excludes_out_of_scope_tagged_service_and_task_definition() -> None:
    ecs = _session().client("ecs")
    stubber = Stubber(ecs)
    cluster = "arn:aws:ecs:eu-west-1:123456789012:cluster/platform"
    service = "arn:aws:ecs:eu-west-1:123456789012:service/platform/other"
    task = "arn:aws:ecs:eu-west-1:123456789012:task-definition/other:1"

    stubber.add_response("list_clusters", {"clusterArns": [cluster]})
    stubber.add_response("describe_clusters", {"clusters": [{"clusterArn": cluster, "clusterName": "platform", "tags": [{"key": "Project", "value": "Test"}], "settings": []}]}, {"clusters": [cluster], "include": ["TAGS", "SETTINGS"]})
    stubber.add_response("list_services", {"serviceArns": [service]}, {"cluster": cluster})
    stubber.add_response("describe_services", {"services": [{"serviceArn": service, "serviceName": "other", "clusterArn": cluster, "taskDefinition": task, "desiredCount": 1, "runningCount": 1, "pendingCount": 0, "tags": [{"key": "Project", "value": "Other"}]}]}, {"cluster": cluster, "services": [service], "include": ["TAGS"]})
    stubber.add_response("list_task_definitions", {"taskDefinitionArns": [task]}, {"status": "ACTIVE"})
    stubber.add_response("describe_task_definition", {"taskDefinition": {"taskDefinitionArn": task, "containerDefinitions": [], "family": "other", "revision": 1, "status": "ACTIVE", "requiresAttributes": [], "compatibilities": []}, "tags": [{"key": "Project", "value": "Other"}]}, {"taskDefinition": task, "include": ["TAGS"]})
    stubber.add_response("describe_capacity_providers", {"capacityProviders": []}, {"include": ["TAGS"]})

    with stubber:
        inventory = AwsInventoryCollector(None, None, ecs_client=ecs)._ecs({"Project": "Test"})

    assert inventory["ECSServices"] == []
    assert inventory["ECSTaskDefinitions"] == []


def test_cloudwatch_log_group_collection_paginates_and_filters_tags() -> None:
    logs = _session().client("logs")
    stubber = Stubber(logs)
    arn_in = "arn:aws:logs:eu-west-1:123456789012:log-group:/ecs/in"
    arn_out = "arn:aws:logs:eu-west-1:123456789012:log-group:/ecs/out"

    stubber.add_response("describe_log_groups", {"logGroups": [{"logGroupName": "/ecs/in", "arn": f"{arn_in}:*", "storedBytes": 0}], "nextToken": "next"})
    stubber.add_response("list_tags_for_resource", {"tags": {"Project": "Test"}}, {"resourceArn": arn_in})
    stubber.add_response("describe_log_groups", {"logGroups": [{"logGroupName": "/ecs/out", "logGroupArn": arn_out, "storedBytes": 0}]}, {"nextToken": "next"})
    stubber.add_response("list_tags_for_resource", {"tags": {"Project": "Other"}}, {"resourceArn": arn_out})

    with stubber:
        groups = AwsInventoryCollector(None, None, logs_client=logs)._log_groups({"Project": "Test"})

    assert [group["logGroupName"] for group in groups] == ["/ecs/in"]
    assert groups[0]["tags"] == {"Project": "Test"}


def test_ecs_collection_uses_only_latest_active_task_definition_revision_per_family() -> None:
    ecs = _session().client("ecs")
    stubber = Stubber(ecs)
    old = "arn:aws:ecs:eu-west-1:123456789012:task-definition/web:1"
    latest = "arn:aws:ecs:eu-west-1:123456789012:task-definition/web:2"

    stubber.add_response("list_clusters", {"clusterArns": []})
    stubber.add_response("list_task_definitions", {"taskDefinitionArns": [old, latest]}, {"status": "ACTIVE"})
    stubber.add_response("describe_task_definition", {"taskDefinition": {"taskDefinitionArn": latest, "containerDefinitions": [], "family": "web", "revision": 2, "status": "ACTIVE", "requiresAttributes": [], "compatibilities": []}, "tags": [{"key": "Project", "value": "Test"}]}, {"taskDefinition": latest, "include": ["TAGS"]})
    stubber.add_response("describe_capacity_providers", {"capacityProviders": []}, {"include": ["TAGS"]})

    with stubber:
        inventory = AwsInventoryCollector(None, None, ecs_client=ecs)._ecs({"Project": "Test"})

    assert [item["revision"] for item in inventory["ECSTaskDefinitions"]] == [2]


def test_ecs_collection_preserves_older_revision_referenced_by_in_scope_service() -> None:
    ecs = _session().client("ecs")
    stubber = Stubber(ecs)
    cluster = "arn:aws:ecs:eu-west-1:123456789012:cluster/platform"
    service = "arn:aws:ecs:eu-west-1:123456789012:service/platform/web"
    old = "arn:aws:ecs:eu-west-1:123456789012:task-definition/web:1"
    latest = "arn:aws:ecs:eu-west-1:123456789012:task-definition/web:2"
    scope_tags = [{"key": "Project", "value": "Test"}]

    stubber.add_response("list_clusters", {"clusterArns": [cluster]})
    stubber.add_response(
        "describe_clusters",
        {"clusters": [{"clusterArn": cluster, "clusterName": "platform", "tags": scope_tags, "settings": []}]},
        {"clusters": [cluster], "include": ["TAGS", "SETTINGS"]},
    )
    stubber.add_response("list_services", {"serviceArns": [service]}, {"cluster": cluster})
    stubber.add_response(
        "describe_services",
        {"services": [{"serviceArn": service, "serviceName": "web", "clusterArn": cluster, "taskDefinition": old, "desiredCount": 1, "runningCount": 1, "pendingCount": 0, "launchType": "FARGATE", "networkConfiguration": {}, "deploymentConfiguration": {}, "tags": []}]},
        {"cluster": cluster, "services": [service], "include": ["TAGS"]},
    )
    stubber.add_response("list_task_definitions", {"taskDefinitionArns": [old, latest]}, {"status": "ACTIVE"})
    stubber.add_response(
        "describe_task_definition",
        {"taskDefinition": {"taskDefinitionArn": old, "containerDefinitions": [], "family": "web", "revision": 1, "networkMode": "awsvpc", "status": "ACTIVE", "requiresAttributes": [], "compatibilities": [], "requiresCompatibilities": []}, "tags": []},
        {"taskDefinition": old, "include": ["TAGS"]},
    )
    stubber.add_response("describe_capacity_providers", {"capacityProviders": []}, {"include": ["TAGS"]})

    with stubber:
        inventory = AwsInventoryCollector(None, None, ecs_client=ecs)._ecs({"Project": "Test"})

    state = {"values": {"root_module": {"resources": [
        {"address": "aws_ecs_cluster.platform", "mode": "managed", "type": "aws_ecs_cluster", "name": "platform", "values": {"arn": cluster, "id": cluster, "name": "platform", "setting": [], "tags": {"Project": "Test"}}},
        {"address": "aws_ecs_task_definition.web", "mode": "managed", "type": "aws_ecs_task_definition", "name": "web", "values": {"arn": old, "family": "web", "revision": 1, "network_mode": "awsvpc", "requires_compatibilities": [], "container_definitions": "[]", "tags": {}}},
        {"address": "aws_ecs_service.web", "mode": "managed", "type": "aws_ecs_service", "name": "web", "values": {"name": "web", "cluster": cluster, "task_definition": old, "desired_count": 1, "launch_type": "FARGATE", "network_configuration": [], "deployment_circuit_breaker": [], "tags": {}}},
    ]}}}
    expected = adapt_terraform_state_with_diagnostics(state).snapshots
    live = adapt_boto3_inventory(inventory)

    assert [item["revision"] for item in inventory["ECSTaskDefinitions"]] == [1]
    assert detect_drift(expected, live) == []


def test_ec2_capacity_provider_collection_paginates_and_inherits_cluster_scope() -> None:
    ecs = _session().client("ecs")
    stubber = Stubber(ecs)
    cluster = "arn:aws:ecs:eu-west-1:123456789012:cluster/platform"
    asg = "arn:aws:autoscaling:eu-west-1:123456789012:autoScalingGroup:asg-id:autoScalingGroupName/ecs-workers"
    scope_tags = [{"key": "Project", "value": "Test"}]

    stubber.add_response("list_clusters", {"clusterArns": [cluster]})
    stubber.add_response(
        "describe_clusters",
        {"clusters": [{"clusterArn": cluster, "clusterName": "platform", "capacityProviders": ["FARGATE", "platform-ec2"], "tags": scope_tags, "settings": []}]},
        {"clusters": [cluster], "include": ["TAGS", "SETTINGS"]},
    )
    stubber.add_response("list_services", {"serviceArns": []}, {"cluster": cluster})
    stubber.add_response("list_task_definitions", {"taskDefinitionArns": []}, {"status": "ACTIVE"})
    stubber.add_response(
        "describe_capacity_providers",
        {"capacityProviders": [
            {"name": "FARGATE", "status": "ACTIVE", "tags": []},
            {"name": "platform-ec2", "status": "ACTIVE", "autoScalingGroupProvider": {"autoScalingGroupArn": asg, "managedScaling": {"status": "ENABLED", "targetCapacity": 80, "minimumScalingStepSize": 1, "maximumScalingStepSize": 4}, "managedTerminationProtection": "DISABLED", "managedDraining": "ENABLED"}, "tags": []},
        ], "nextToken": "next"},
        {"include": ["TAGS"]},
    )
    stubber.add_response(
        "describe_capacity_providers",
        {"capacityProviders": [{"name": "other-ec2", "status": "ACTIVE", "autoScalingGroupProvider": {"autoScalingGroupArn": asg, "managedScaling": {"status": "ENABLED", "targetCapacity": 100, "minimumScalingStepSize": 1, "maximumScalingStepSize": 1}, "managedTerminationProtection": "DISABLED", "managedDraining": "ENABLED"}, "tags": [{"key": "Project", "value": "Other"}]}]},
        {"include": ["TAGS"], "nextToken": "next"},
    )

    with stubber:
        inventory = AwsInventoryCollector(None, None, ecs_client=ecs)._ecs({"Project": "Test"})

    assert [item["name"] for item in inventory["ECSCapacityProviders"]] == ["platform-ec2"]
    assert inventory["ECSCapacityProviders"][0]["tags"] == scope_tags
