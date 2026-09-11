"""Read AWS inventory and return the boto3-shaped contract used by the adapter."""

from __future__ import annotations

from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class AwsCollectionError(RuntimeError):
    """AWS inventory collection failed before a complete scan could be built."""


class AwsInventoryCollector:
    """Collect only describe/list/get APIs required by Sprint 2 coverage."""

    def __init__(self, ec2_client: Any, s3_client: Any) -> None:
        self.ec2_client = ec2_client
        self.s3_client = s3_client

    def collect(self, tag_scope: dict[str, str] | None = None) -> dict[str, Any]:
        tag_scope = tag_scope or {}
        try:
            return {
                "SecurityGroups": self._collect_security_groups(tag_scope),
                "Buckets": self._collect_buckets(tag_scope),
                "Reservations": self._collect_reservations(tag_scope),
            }
        except (BotoCoreError, ClientError) as error:
            raise AwsCollectionError(f"Read-only AWS inventory collection failed: {error}") from error

    def _collect_security_groups(self, tag_scope: dict[str, str]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for page in self.ec2_client.get_paginator("describe_security_groups").paginate(**_ec2_tag_filters(tag_scope)):
            groups.extend(page.get("SecurityGroups", []))
        return groups

    def _collect_reservations(self, tag_scope: dict[str, str]) -> list[dict[str, Any]]:
        reservations: list[dict[str, Any]] = []
        for page in self.ec2_client.get_paginator("describe_instances").paginate(**_ec2_tag_filters(tag_scope)):
            reservations.extend(page.get("Reservations", []))
        return reservations

    def _collect_buckets(self, tag_scope: dict[str, str]) -> list[dict[str, Any]]:
        buckets: list[dict[str, Any]] = []
        for bucket in self.s3_client.list_buckets().get("Buckets", []):
            name = bucket["Name"]
            enriched = dict(bucket)
            enriched["PublicAccessBlockConfiguration"] = self._public_access_block(name)
            enriched["BucketEncryption"] = self._bucket_encryption(name)
            enriched["Tags"] = self._bucket_tags(name)
            if _matches_tag_scope(enriched["Tags"], tag_scope):
                buckets.append(enriched)
        return buckets

    def _public_access_block(self, bucket: str) -> dict[str, Any]:
        try:
            return self.s3_client.get_public_access_block(Bucket=bucket).get("PublicAccessBlockConfiguration", {})
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"NoSuchPublicAccessBlockConfiguration", "NoSuchBucket"}:
                return {}
            raise

    def _bucket_encryption(self, bucket: str) -> dict[str, Any]:
        try:
            response = self.s3_client.get_bucket_encryption(Bucket=bucket)
            return {"Rules": response.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])}
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"ServerSideEncryptionConfigurationNotFoundError", "NoSuchBucket"}:
                return {"Rules": []}
            raise

    def _bucket_tags(self, bucket: str) -> list[dict[str, str]]:
        try:
            return self.s3_client.get_bucket_tagging(Bucket=bucket).get("TagSet", [])
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"NoSuchTagSet", "NoSuchBucket"}:
                return []
            raise


def collect_live_inventory(
    profile: str | None,
    region: str,
    role_arn: str | None,
    tag_scope: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build an AWS session and collect inventory without any mutation APIs."""
    session = _build_session(profile, region, role_arn)
    return AwsInventoryCollector(session.client("ec2", region_name=region), session.client("s3", region_name=region)).collect(tag_scope)


def _ec2_tag_filters(tag_scope: dict[str, str]) -> dict[str, list[dict[str, list[str]]]]:
    if not tag_scope:
        return {}
    return {"Filters": [{"Name": f"tag:{key}", "Values": [value]} for key, value in sorted(tag_scope.items())]}


def _matches_tag_scope(tags: list[dict[str, str]], tag_scope: dict[str, str]) -> bool:
    if not tag_scope:
        return True
    tag_map = {tag.get("Key"): tag.get("Value") for tag in tags}
    return all(tag_map.get(key) == value for key, value in tag_scope.items())


def _build_session(profile: str | None, region: str, role_arn: str | None) -> boto3.Session:
    base_session = boto3.Session(profile_name=profile, region_name=region)
    if not role_arn:
        return base_session
    try:
        credentials = base_session.client("sts", region_name=region).assume_role(
            RoleArn=role_arn,
            RoleSessionName="driftctl-read-only",
        )["Credentials"]
    except (BotoCoreError, ClientError) as error:
        raise AwsCollectionError(f"Unable to assume read-only role: {error}") from error
    return boto3.Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
        region_name=region,
    )
