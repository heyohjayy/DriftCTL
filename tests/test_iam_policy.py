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
