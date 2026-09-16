import copy
import json

from driftctl.adapters.boto3_snapshots import adapt_boto3_inventory
from driftctl.adapters.terraform_state import adapt_terraform_state_with_diagnostics
from driftctl.detector import detect_drift
from driftctl.models import DriftType, Severity
from driftctl.presentation import ImpactLevel, assess_impacts, explain_finding, readable_resource_type
from driftctl.severity_rules import classify_finding, default_rules


CLUSTER_ARN = "arn:aws:ecs:eu-west-1:123456789012:cluster/platform"
TASK_ARN = "arn:aws:ecs:eu-west-1:123456789012:task-definition/web:1"


def _state() -> dict:
    containers = [{
        "name": "web",
        "image": "123456789012.dkr.ecr.eu-west-1.amazonaws.com/web:1",
        "essential": True,
        "portMappings": [{"containerPort": 8080, "protocol": "tcp"}],
        "environment": [{"name": "B", "value": "2"}, {"name": "A", "value": "1"}],
        "logConfiguration": {"logDriver": "awslogs", "options": {"awslogs-region": "eu-west-1", "awslogs-group": "/ecs/web"}},
    }]
    return {"values": {"root_module": {"resources": [
        {"address": "aws_ecs_cluster.platform", "mode": "managed", "type": "aws_ecs_cluster", "name": "platform", "values": {"arn": CLUSTER_ARN, "id": CLUSTER_ARN, "name": "platform", "setting": [{"name": "containerInsights", "value": "enabled"}], "tags": {"Project": "Test"}}},
        {"address": "aws_ecs_task_definition.web", "mode": "managed", "type": "aws_ecs_task_definition", "name": "web", "values": {"arn": TASK_ARN, "family": "web", "revision": 1, "network_mode": "awsvpc", "requires_compatibilities": ["FARGATE"], "cpu": "256", "memory": "512", "execution_role_arn": "arn:aws:iam::123456789012:role/ecs-execution", "task_role_arn": None, "runtime_platform": [{"cpu_architecture": "X86_64", "operating_system_family": "LINUX"}], "container_definitions": json.dumps(containers), "tags": {}}},
        {"address": "aws_ecs_service.web", "mode": "managed", "type": "aws_ecs_service", "name": "web", "values": {"name": "web", "cluster": CLUSTER_ARN, "task_definition": TASK_ARN, "desired_count": 2, "launch_type": "FARGATE", "network_configuration": [{"subnets": ["subnet-b", "subnet-a"], "security_groups": ["sg-app"], "assign_public_ip": False}], "deployment_minimum_healthy_percent": 100, "deployment_maximum_percent": 200, "deployment_circuit_breaker": [{"enable": True, "rollback": True}], "scheduling_strategy": "REPLICA", "enable_execute_command": False, "load_balancer": [], "tags": {}}},
        {"address": "aws_cloudwatch_log_group.web", "mode": "managed", "type": "aws_cloudwatch_log_group", "name": "web", "values": {"name": "/ecs/web", "retention_in_days": 30, "kms_key_id": None, "log_group_class": "STANDARD", "tags": {"Project": "Test"}}},
    ]}}}


def _live() -> dict:
    return {
        "ECSClusters": [{"clusterArn": CLUSTER_ARN, "clusterName": "platform", "settings": [{"name": "containerInsights", "value": "enabled"}], "tags": [{"key": "Project", "value": "Test"}]}],
        "ECSTaskDefinitions": [{"taskDefinitionArn": TASK_ARN, "family": "web", "revision": 1, "networkMode": "awsvpc", "requiresCompatibilities": ["FARGATE"], "cpu": "256", "memory": "512", "executionRoleArn": "arn:aws:iam::123456789012:role/ecs-execution", "runtimePlatform": {"cpuArchitecture": "X86_64", "operatingSystemFamily": "LINUX"}, "containerDefinitions": [{"name": "web", "image": "123456789012.dkr.ecr.eu-west-1.amazonaws.com/web:1", "cpu": 0, "essential": True, "portMappings": [{"containerPort": 8080, "hostPort": 8080, "protocol": "tcp"}], "environment": [{"name": "A", "value": "1"}, {"name": "B", "value": "2"}], "logConfiguration": {"logDriver": "awslogs", "options": {"awslogs-group": "/ecs/web", "awslogs-region": "eu-west-1"}}}]}],
        "ECSServices": [{"serviceArn": "arn:aws:ecs:eu-west-1:123456789012:service/platform/web", "serviceName": "web", "clusterArn": CLUSTER_ARN, "taskDefinition": TASK_ARN, "desiredCount": 2, "launchType": "FARGATE", "networkConfiguration": {"awsvpcConfiguration": {"subnets": ["subnet-a", "subnet-b"], "securityGroups": ["sg-app"], "assignPublicIp": "DISABLED"}}, "deploymentConfiguration": {"minimumHealthyPercent": 100, "maximumPercent": 200, "deploymentCircuitBreaker": {"enable": True, "rollback": True}}, "schedulingStrategy": "REPLICA", "enableExecuteCommand": False, "loadBalancers": [], "tags": []}],
        "LogGroups": [{"logGroupName": "/ecs/web", "arn": "arn:aws:logs:eu-west-1:123456789012:log-group:/ecs/web:*", "retentionInDays": 30, "logGroupClass": "STANDARD", "tags": {"Project": "Test"}}],
    }


def _snapshots() -> tuple[list, list]:
    return adapt_terraform_state_with_diagnostics(_state()).snapshots, adapt_boto3_inventory(_live())


def test_matching_ecs_fargate_and_log_inventory_has_no_drift() -> None:
    expected, live = _snapshots()

    assert detect_drift(expected, live) == []
    assert {snapshot.identity.resource_type for snapshot in expected} == {"ecs_cluster", "ecs_task_definition", "ecs_service", "cloudwatch_log_group"}


def test_ecs_service_network_change_is_modified_and_public_ip_is_moderate() -> None:
    live_payload = _live()
    network = live_payload["ECSServices"][0]["networkConfiguration"]["awsvpcConfiguration"]
    network["assignPublicIp"] = "ENABLED"
    network["securityGroups"] = ["sg-public"]

    findings = detect_drift(adapt_terraform_state_with_diagnostics(_state()).snapshots, adapt_boto3_inventory(live_payload))
    finding = next(item for item in findings if item.identity.resource_type == "ecs_service")
    classify_finding(finding, default_rules())

    assert finding.drift_type is DriftType.MODIFIED
    assert "network_configuration" in finding.changes
    assert finding.severity is Severity.MODERATE
    assert "EcsPublicIpRule" in finding.severity_reason
    assert assess_impacts(finding).security is ImpactLevel.LOW
    assert "assign public IP addresses" in explain_finding(finding).change


def test_desired_count_only_drift_does_not_report_unchanged_public_ip_as_risk() -> None:
    state = _state()
    expected_service = next(
        resource
        for resource in state["values"]["root_module"]["resources"]
        if resource["type"] == "aws_ecs_service"
    )
    expected_service["values"]["network_configuration"][0]["assign_public_ip"] = True
    live = _live()
    live_service = live["ECSServices"][0]
    live_service["networkConfiguration"]["awsvpcConfiguration"]["assignPublicIp"] = "ENABLED"
    live_service["desiredCount"] = 3

    findings = detect_drift(
        adapt_terraform_state_with_diagnostics(state).snapshots,
        adapt_boto3_inventory(live),
    )
    finding = next(item for item in findings if item.identity.resource_type == "ecs_service")
    classify_finding(finding, default_rules())
    impact = assess_impacts(finding)
    explanation = explain_finding(finding)

    assert finding.changes == {"desired_count": {"expected": 2, "live": 3}}
    assert finding.severity is Severity.MODERATE
    assert "DefaultModifiedRule" in finding.severity_reason
    assert finding.remediation.summary == "Reconcile the approved state without applying automatically."
    assert "differs from Terraform in: desired_count" in explanation.change
    assert "public IP" not in explanation.change
    assert (impact.security, impact.cost, impact.availability) == (
        ImpactLevel.NOT_ASSESSED,
        ImpactLevel.NOT_ASSESSED,
        ImpactLevel.NOT_ASSESSED,
    )


def test_ecs_desired_count_one_to_zero_has_high_availability_impact() -> None:
    state = _state()
    expected_service = next(
        resource
        for resource in state["values"]["root_module"]["resources"]
        if resource["type"] == "aws_ecs_service"
    )
    expected_service["values"]["desired_count"] = 1
    live = _live()
    live["ECSServices"][0]["desiredCount"] = 0

    findings = detect_drift(
        adapt_terraform_state_with_diagnostics(state).snapshots,
        adapt_boto3_inventory(live),
    )
    finding = next(item for item in findings if item.identity.resource_type == "ecs_service")
    classify_finding(finding, default_rules())
    impact = assess_impacts(finding)

    assert finding.changes == {"desired_count": {"expected": 1, "live": 0}}
    assert finding.severity is Severity.MODERATE
    assert "DefaultModifiedRule" in finding.severity_reason
    assert (impact.security, impact.cost, impact.availability) == (
        ImpactLevel.NOT_ASSESSED,
        ImpactLevel.NONE,
        ImpactLevel.HIGH,
    )


def test_unmanaged_ecs_service_with_public_ip_keeps_public_ip_guidance() -> None:
    live = _live()
    unmanaged = copy.deepcopy(live["ECSServices"][0])
    unmanaged["serviceName"] = "console-service"
    unmanaged["serviceArn"] = "arn:aws:ecs:eu-west-1:123456789012:service/platform/console-service"
    unmanaged["networkConfiguration"]["awsvpcConfiguration"]["assignPublicIp"] = "ENABLED"
    live["ECSServices"].append(unmanaged)

    findings = detect_drift(
        adapt_terraform_state_with_diagnostics(_state()).snapshots,
        adapt_boto3_inventory(live),
    )
    finding = next(item for item in findings if item.identity.name == "platform|console-service")
    classify_finding(finding, default_rules())

    assert finding.drift_type is DriftType.UNMANAGED
    assert "EcsPublicIpRule" in finding.severity_reason
    assert "assign public IP addresses" in explain_finding(finding).change
    assert assess_impacts(finding).security is ImpactLevel.LOW


def test_ecs_missing_and_in_scope_unmanaged_resources_are_detected() -> None:
    live_payload = _live()
    live_payload["LogGroups"] = []
    unmanaged = copy.deepcopy(live_payload["ECSServices"][0])
    unmanaged.update({"serviceName": "console-service", "serviceArn": "arn:aws:ecs:eu-west-1:123456789012:service/platform/console-service"})
    unmanaged["tags"] = [{"key": "Project", "value": "Test"}]
    live_payload["ECSServices"].append(unmanaged)

    findings = detect_drift(adapt_terraform_state_with_diagnostics(_state()).snapshots, adapt_boto3_inventory(live_payload))

    assert any(item.identity.resource_type == "cloudwatch_log_group" and item.drift_type is DriftType.MISSING for item in findings)
    assert any(item.identity.name == "platform|console-service" and item.drift_type is DriftType.UNMANAGED for item in findings)


def test_task_definition_container_json_is_structurally_normalized() -> None:
    expected, live = _snapshots()
    expected_task = next(item for item in expected if item.identity.resource_type == "ecs_task_definition")
    live_task = next(item for item in live if item.identity.resource_type == "ecs_task_definition")

    assert expected_task.attributes == live_task.attributes
    assert [item["name"] for item in live_task.attributes["container_definitions"][0]["environment"]] == ["A", "B"]


def test_log_retention_regression_has_conservative_policy_and_display_label() -> None:
    live_payload = _live()
    live_payload["LogGroups"][0].pop("retentionInDays")
    findings = detect_drift(adapt_terraform_state_with_diagnostics(_state()).snapshots, adapt_boto3_inventory(live_payload))
    finding = next(item for item in findings if item.identity.resource_type == "cloudwatch_log_group")

    classify_finding(finding, default_rules())

    assert finding.severity is Severity.MODERATE
    assert "LogRetentionChangeRule" in finding.severity_reason
    assert assess_impacts(finding).cost is ImpactLevel.LOW
    assert readable_resource_type(finding.identity.resource_type) == "AWS CloudWatch Log Group"


def test_blank_terraform_log_group_kms_key_matches_absent_aws_kms_key() -> None:
    state = _state()
    log_group = next(
        resource
        for resource in state["values"]["root_module"]["resources"]
        if resource["type"] == "aws_cloudwatch_log_group"
    )
    log_group["values"]["kms_key_id"] = ""

    findings = detect_drift(
        adapt_terraform_state_with_diagnostics(state).snapshots,
        adapt_boto3_inventory(_live()),
    )

    assert not any(item.identity.resource_type == "cloudwatch_log_group" for item in findings)


def test_real_log_group_kms_key_difference_remains_modified() -> None:
    state = _state()
    log_group = next(
        resource
        for resource in state["values"]["root_module"]["resources"]
        if resource["type"] == "aws_cloudwatch_log_group"
    )
    log_group["values"]["kms_key_id"] = ""
    live = _live()
    live["LogGroups"][0]["kmsKeyId"] = "arn:aws:kms:eu-west-1:123456789012:key/live-key"

    findings = detect_drift(
        adapt_terraform_state_with_diagnostics(state).snapshots,
        adapt_boto3_inventory(live),
    )
    finding = next(item for item in findings if item.identity.resource_type == "cloudwatch_log_group")

    assert finding.drift_type is DriftType.MODIFIED
    assert finding.changes["kms_key_id"] == {
        "expected": None,
        "live": "arn:aws:kms:eu-west-1:123456789012:key/live-key",
    }
