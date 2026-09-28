import boto3
from botocore.stub import Stubber

from driftctl.collectors.aws import AwsInventoryCollector


def _session() -> boto3.Session:
    return boto3.Session(
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        region_name="eu-west-1",
    )


def _function(name: str) -> dict:
    return {
        "FunctionName": name,
        "FunctionArn": f"arn:aws:lambda:eu-west-1:123456789012:function:{name}",
        "Runtime": "python3.13",
        "Role": "arn:aws:iam::123456789012:role/lambda",
        "Handler": "app.handler",
        "CodeSize": 100,
        "Description": "",
        "Timeout": 3,
        "MemorySize": 128,
        "LastModified": "2026-09-28T00:00:00.000+0000",
        "CodeSha256": "hash",
        "Version": "$LATEST",
        "PackageType": "Zip",
        "Architectures": ["x86_64"],
        "EphemeralStorage": {"Size": 512},
    }


def test_lambda_collection_paginates_and_applies_tag_scope() -> None:
    client = _session().client("lambda")
    stubber = Stubber(client)
    in_scope = _function("in-scope")
    out_scope = _function("out-scope")
    stubber.add_response(
        "list_functions",
        {"Functions": [in_scope], "NextMarker": "next"},
    )
    stubber.add_response(
        "list_tags",
        {"Tags": {"Project": "Test"}},
        {"Resource": in_scope["FunctionArn"]},
    )
    stubber.add_response(
        "get_function_concurrency",
        {"ReservedConcurrentExecutions": 2},
        {"FunctionName": "in-scope"},
    )
    stubber.add_response(
        "list_functions",
        {"Functions": [out_scope]},
        {"Marker": "next"},
    )
    stubber.add_response(
        "list_tags",
        {"Tags": {"Project": "Other"}},
        {"Resource": out_scope["FunctionArn"]},
    )

    with stubber:
        functions = AwsInventoryCollector(
            None,
            None,
            lambda_client=client,
        )._lambda_functions({"Project": "Test"})

    assert [item["FunctionName"] for item in functions] == ["in-scope"]
    assert functions[0]["ReservedConcurrentExecutions"] == 2


def test_eventbridge_collection_inherits_scoped_rule_to_targets_and_diagnoses_other_rules() -> None:
    client = _session().client("events")
    stubber = Stubber(client)
    scheduled_arn = (
        "arn:aws:events:eu-west-1:123456789012:rule/driftctl-schedule"
    )
    out_arn = "arn:aws:events:eu-west-1:123456789012:rule/out-schedule"
    event_arn = "arn:aws:events:eu-west-1:123456789012:rule/event-pattern"
    stubber.add_response(
        "list_rules",
        {
            "Rules": [
                {
                    "Name": "driftctl-schedule",
                    "Arn": scheduled_arn,
                    "State": "ENABLED",
                    "ScheduleExpression": "rate(5 minutes)",
                    "EventBusName": "default",
                },
                {
                    "Name": "out-schedule",
                    "Arn": out_arn,
                    "State": "ENABLED",
                    "ScheduleExpression": "rate(1 hour)",
                    "EventBusName": "default",
                },
                {
                    "Name": "event-pattern",
                    "Arn": event_arn,
                    "State": "ENABLED",
                    "EventPattern": "{\"source\":[\"demo\"]}",
                    "EventBusName": "default",
                },
            ]
        },
        {"EventBusName": "default"},
    )
    stubber.add_response(
        "list_tags_for_resource",
        {"Tags": [{"Key": "Project", "Value": "Test"}]},
        {"ResourceARN": scheduled_arn},
    )
    stubber.add_response(
        "list_targets_by_rule",
        {
            "Targets": [{
                "Id": "lambda",
                "Arn": "arn:aws:lambda:eu-west-1:123456789012:function:job",
            }]
        },
        {"Rule": "driftctl-schedule", "EventBusName": "default"},
    )
    stubber.add_response(
        "list_tags_for_resource",
        {"Tags": [{"Key": "Project", "Value": "Other"}]},
        {"ResourceARN": out_arn},
    )
    collector = AwsInventoryCollector(None, None, events_client=client)

    with stubber:
        rules = collector._eventbridge_rules({"Project": "Test"})

    assert [item["Name"] for item in rules] == ["driftctl-schedule"]
    assert [item["Id"] for item in rules[0]["Targets"]] == ["lambda"]
    assert collector.diagnostics == [{
        "source": "aws_collection",
        "message": (
            "Skipped EventBridge rule event-pattern because only scheduled rules are supported."
        ),
    }]
