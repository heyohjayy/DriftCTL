import json
from pathlib import Path


POLICY_PATH = (
    Path(__file__).parents[1] / "infra" / "iam" / "driftctl-read-only-policy.json"
)


def test_s3_encryption_uses_the_iam_action_name() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    actions = {
        action
        for statement in policy["Statement"]
        for action in (
            [statement["Action"]]
            if isinstance(statement["Action"], str)
            else statement["Action"]
        )
    }

    assert "s3:GetEncryptionConfiguration" in actions
    assert "s3:GetBucketEncryption" not in actions


def test_compute_and_event_collection_permissions_are_read_only() -> None:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    actions = {
        action
        for statement in policy["Statement"]
        for action in (
            [statement["Action"]]
            if isinstance(statement["Action"], str)
            else statement["Action"]
        )
    }

    assert {
        "ecs:DescribeCapacityProviders",
        "ecs:DescribeClusters",
        "ecs:DescribeServices",
        "ecs:DescribeTaskDefinition",
        "ecs:ListClusters",
        "ecs:ListServices",
        "ecs:ListTagsForResource",
        "ecs:ListTaskDefinitions",
        "logs:DescribeLogGroups",
        "logs:ListTagsForResource",
        "lambda:GetFunctionConcurrency",
        "lambda:ListFunctions",
        "lambda:ListTags",
        "events:ListRules",
        "events:ListTagsForResource",
        "events:ListTargetsByRule",
        "eks:DescribeCluster",
        "eks:DescribeNodegroup",
        "eks:ListClusters",
        "eks:ListNodegroups",
    } <= actions
    assert all(
        not action.startswith(
            (
                "ecs:Create",
                "ecs:Delete",
                "ecs:Deregister",
                "ecs:Register",
                "ecs:Run",
                "ecs:Start",
                "ecs:Stop",
                "ecs:Update",
                "logs:Create",
                "logs:Delete",
                "logs:Put",
                "lambda:Create",
                "lambda:Delete",
                "lambda:Invoke",
                "lambda:Put",
                "lambda:Update",
                "events:Delete",
                "events:Disable",
                "events:Enable",
                "events:Put",
                "events:Remove",
                "eks:Associate",
                "eks:Create",
                "eks:Delete",
                "eks:Deregister",
                "eks:Register",
                "eks:Tag",
                "eks:Untag",
                "eks:Update",
            )
        )
        for action in actions
    )
