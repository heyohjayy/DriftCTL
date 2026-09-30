import copy
import json

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


ROLE_ARN = "arn:aws:iam::123456789012:role/driftctl-lambda"
FUNCTION_ARN = "arn:aws:lambda:eu-west-1:123456789012:function:driftctl-job"
RULE_ARN = "arn:aws:events:eu-west-1:123456789012:rule/driftctl-schedule"


def _state() -> dict:
    trust = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }
    return {"values": {"root_module": {"resources": [
        {
            "address": "aws_iam_role.lambda",
            "mode": "managed",
            "type": "aws_iam_role",
            "name": "lambda",
            "values": {
                "name": "driftctl-lambda",
                "assume_role_policy": json.dumps(trust),
                "tags": {"Project": "Test"},
            },
        },
        {
            "address": "aws_lambda_function.job",
            "mode": "managed",
            "type": "aws_lambda_function",
            "name": "job",
            "values": {
                "function_name": "driftctl-job",
                "runtime": "python3.13",
                "handler": "app.handler",
                "role": ROLE_ARN,
                "memory_size": 256,
                "timeout": 30,
                "package_type": "Zip",
                "architectures": ["x86_64"],
                "reserved_concurrent_executions": -1,
                "environment": [{"variables": {"MODE": "demo", "PROJECT": "Test"}}],
                "tracing_config": [{"mode": "PassThrough"}],
                "ephemeral_storage": [{"size": 512}],
                "vpc_config": [],
                "dead_letter_config": [],
                "layers": [],
                "kms_key_arn": "",
                "description": "Scheduled validation function",
                "tags": {"Project": "Test"},
            },
        },
        {
            "address": "aws_cloudwatch_log_group.lambda",
            "mode": "managed",
            "type": "aws_cloudwatch_log_group",
            "name": "lambda",
            "values": {
                "name": "/aws/lambda/driftctl-job",
                "retention_in_days": 7,
                "kms_key_id": None,
                "log_group_class": "STANDARD",
                "tags": {"Project": "Test"},
            },
        },
        {
            "address": "aws_cloudwatch_event_rule.schedule",
            "mode": "managed",
            "type": "aws_cloudwatch_event_rule",
            "name": "schedule",
            "values": {
                "name": "driftctl-schedule",
                "arn": RULE_ARN,
                "event_bus_name": "default",
                "schedule_expression": "rate(5 minutes)",
                "is_enabled": True,
                "role_arn": "",
                "description": "Invoke the validation function",
                "tags": {"Project": "Test"},
            },
        },
        {
            "address": "aws_cloudwatch_event_target.lambda",
            "mode": "managed",
            "type": "aws_cloudwatch_event_target",
            "name": "lambda",
            "values": {
                "rule": "driftctl-schedule",
                "event_bus_name": "default",
                "target_id": "lambda",
                "arn": FUNCTION_ARN,
                "role_arn": "",
                "input": "{\"source\":\"driftctl\"}",
                "input_path": "",
                "input_transformer": [],
                "retry_policy": [],
                "dead_letter_config": [],
            },
        },
    ]}}}


def _live() -> dict:
    return {
        "IamRoles": [{
            "RoleName": "driftctl-lambda",
            "AssumeRolePolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }],
            },
            "ManagedPolicyArns": [],
            "InlinePolicies": [],
            "Tags": [{"Key": "Project", "Value": "Test"}],
        }],
        "LambdaFunctions": [{
            "FunctionName": "driftctl-job",
            "FunctionArn": FUNCTION_ARN,
            "Runtime": "python3.13",
            "Role": ROLE_ARN,
            "Handler": "app.handler",
            "Description": "Scheduled validation function",
            "Timeout": 30,
            "MemorySize": 256,
            "PackageType": "Zip",
            "Architectures": ["x86_64"],
            "ReservedConcurrentExecutions": -1,
            "Environment": {"Variables": {"PROJECT": "Test", "MODE": "demo"}},
            "TracingConfig": {"Mode": "PassThrough"},
            "EphemeralStorage": {"Size": 512},
            "VpcConfig": {"SubnetIds": [], "SecurityGroupIds": []},
            "Tags": {"Project": "Test"},
        }],
        "LogGroups": [{
            "logGroupName": "/aws/lambda/driftctl-job",
            "retentionInDays": 7,
            "logGroupClass": "STANDARD",
            "tags": {"Project": "Test"},
        }],
        "EventBridgeRules": [{
            "Name": "driftctl-schedule",
            "Arn": RULE_ARN,
            "EventBusName": "default",
            "ScheduleExpression": "rate(5 minutes)",
            "State": "ENABLED",
            "Description": "Invoke the validation function",
            "Tags": [{"Key": "Project", "Value": "Test"}],
            "Targets": [{
                "Id": "lambda",
                "Arn": FUNCTION_ARN,
                "Input": "{\"source\":\"driftctl\"}",
            }],
        }],
    }


def test_matching_lambda_schedule_role_and_logs_have_no_drift() -> None:
    expected = adapt_terraform_state_with_diagnostics(_state())
    findings = detect_drift(expected.snapshots, adapt_boto3_inventory(_live()))

    assert expected.diagnostics == ()
    assert findings == []
    assert {item.identity.resource_type for item in expected.snapshots} == {
        "iam_role",
        "lambda_function",
        "cloudwatch_log_group",
        "eventbridge_scheduled_rule",
    }


def test_lambda_role_deduplicates_inline_policy_reported_by_role_and_child() -> None:
    state = _state()
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "WriteFunctionLogs",
            "Effect": "Allow",
            "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
            "Resource": "arn:aws:logs:eu-west-1:123456789012:log-group:/aws/lambda/driftctl-job:*",
        }],
    }
    role = state["values"]["root_module"]["resources"][0]
    role["values"]["inline_policy"] = [{
        "name": "driftctl-lambda-logs",
        "policy": json.dumps(policy),
    }]
    state["values"]["root_module"]["resources"].append({
        "address": "aws_iam_role_policy.lambda_logs",
        "mode": "managed",
        "type": "aws_iam_role_policy",
        "name": "lambda_logs",
        "values": {
            "name": "driftctl-lambda-logs",
            "role": "driftctl-lambda",
            "policy": json.dumps(policy),
        },
    })

    role_snapshot = next(
        snapshot
        for snapshot in adapt_terraform_state_with_diagnostics(state).snapshots
        if snapshot.identity.resource_type == "iam_role"
    )

    assert role_snapshot.attributes["inline_policies"] == [{
        "name": "driftctl-lambda-logs",
        "document": policy,
    }]


def test_lambda_execution_role_change_has_specific_risk_guidance() -> None:
    live = _live()
    live["LambdaFunctions"][0]["Role"] = "arn:aws:iam::123456789012:role/unapproved"
    finding = next(
        item
        for item in detect_drift(
            adapt_terraform_state_with_diagnostics(_state()).snapshots,
            adapt_boto3_inventory(live),
        )
        if item.identity.resource_type == "lambda_function"
    )
    classify_finding(finding, default_rules())

    assert finding.drift_type is DriftType.MODIFIED
    assert set(finding.changes) == {"role_arn"}
    assert finding.severity is Severity.SEVERE
    assert "LambdaExecutionRoleChangeRule" in finding.severity_reason
    assert assess_impacts(finding).security is ImpactLevel.HIGH
    assert "different execution role" in explain_finding(finding).change
    assert readable_resource_type("lambda_function") == "AWS Lambda Function"


def test_disabled_eventbridge_schedule_and_changed_target_remain_real_drift() -> None:
    live = _live()
    live["EventBridgeRules"][0]["State"] = "DISABLED"
    live["EventBridgeRules"][0]["Targets"][0]["Arn"] = (
        "arn:aws:lambda:eu-west-1:123456789012:function:other"
    )
    finding = next(
        item
        for item in detect_drift(
            adapt_terraform_state_with_diagnostics(_state()).snapshots,
            adapt_boto3_inventory(live),
        )
        if item.identity.resource_type == "eventbridge_scheduled_rule"
    )
    classify_finding(finding, default_rules())

    assert set(finding.changes) == {"enabled", "targets"}
    assert finding.severity is Severity.SEVERE
    assert "EventBridgeScheduleChangeRule" in finding.severity_reason
    assert assess_impacts(finding).availability is ImpactLevel.HIGH
    assert "unexpected time" in explain_finding(finding).consequence
    assert (
        readable_resource_type("eventbridge_scheduled_rule")
        == "AWS EventBridge Scheduled Rule"
    )


def test_in_scope_unmanaged_lambda_and_schedule_are_detected() -> None:
    live = _live()
    unmanaged_function = copy.deepcopy(live["LambdaFunctions"][0])
    unmanaged_function["FunctionName"] = "console-function"
    unmanaged_function["FunctionArn"] = (
        "arn:aws:lambda:eu-west-1:123456789012:function:console-function"
    )
    live["LambdaFunctions"].append(unmanaged_function)
    unmanaged_rule = copy.deepcopy(live["EventBridgeRules"][0])
    unmanaged_rule["Name"] = "console-schedule"
    unmanaged_rule["Arn"] = (
        "arn:aws:events:eu-west-1:123456789012:rule/console-schedule"
    )
    live["EventBridgeRules"].append(unmanaged_rule)

    findings = detect_drift(
        adapt_terraform_state_with_diagnostics(_state()).snapshots,
        adapt_boto3_inventory(live),
    )

    assert {
        item.identity.resource_type
        for item in findings
        if item.drift_type is DriftType.UNMANAGED
    } == {"lambda_function", "eventbridge_scheduled_rule"}


def test_non_scheduled_rule_and_target_are_explicitly_skipped() -> None:
    state = _state()
    resources = state["values"]["root_module"]["resources"]
    resources.extend([
        {
            "address": "aws_cloudwatch_event_rule.events",
            "mode": "managed",
            "type": "aws_cloudwatch_event_rule",
            "name": "events",
            "values": {
                "name": "events",
                "event_pattern": "{\"source\":[\"demo\"]}",
                "tags": {"Project": "Test"},
            },
        },
        {
            "address": "aws_cloudwatch_event_target.events",
            "mode": "managed",
            "type": "aws_cloudwatch_event_target",
            "name": "events",
            "values": {"rule": "events", "target_id": "lambda", "arn": FUNCTION_ARN},
        },
    ])

    result = adapt_terraform_state_with_diagnostics(state)

    assert not any(item.identity.name == "events" for item in result.snapshots)
    assert [item.message for item in result.diagnostics] == [
        "Skipped EventBridge target because its parent is not a supported scheduled rule.",
        "Skipped EventBridge rule because only scheduled rules are supported.",
    ]
