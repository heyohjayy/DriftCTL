"""Read-only AWS inventory collector; no mutation API is called."""

from __future__ import annotations

from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class AwsCollectionError(RuntimeError): pass


class AwsInventoryCollector:
    def __init__(self, ec2_client: Any, s3_client: Any, iam_client: Any | None = None, route53_client: Any | None = None) -> None:
        self.ec2_client, self.s3_client, self.iam_client, self.route53_client = ec2_client, s3_client, iam_client, route53_client
        self.diagnostics: list[dict[str, str]] = []

    def collect(self, tag_scope: dict[str, str] | None = None) -> dict[str, Any]:
        scope = tag_scope or {}
        try:
            inventory = {
                "SecurityGroups": self._ec2("describe_security_groups", "SecurityGroups", scope),
                "Buckets": self._buckets(scope),
                "Reservations": self._ec2("describe_instances", "Reservations", scope),
                "Vpcs": self._ec2("describe_vpcs", "Vpcs", scope),
                "Subnets": self._ec2("describe_subnets", "Subnets", scope),
                "InternetGateways": self._ec2("describe_internet_gateways", "InternetGateways", scope),
                "RouteTables": self._ec2("describe_route_tables", "RouteTables", scope),
                "NetworkAcls": self._ec2("describe_network_acls", "NetworkAcls", scope),
                "IamRoles": self._roles(scope) if self.iam_client else [],
                "InstanceProfiles": self._profiles(scope) if self.iam_client else [],
                "HostedZones": [], "RecordSets": {}, "CollectionDiagnostics": self.diagnostics,
            }
            if self.route53_client: inventory["HostedZones"], inventory["RecordSets"] = self._zones(scope)
            return inventory
        except (BotoCoreError, ClientError) as error:
            raise AwsCollectionError(f"Read-only AWS inventory collection failed: {error}") from error

    def _ec2(self, operation: str, result_key: str, scope: dict[str, str]) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        for page in self.ec2_client.get_paginator(operation).paginate(**_ec2_filters(scope)): values.extend(page.get(result_key, []))
        return values

    def _buckets(self, scope: dict[str, str]) -> list[dict[str, Any]]:
        values = []
        for bucket in self.s3_client.list_buckets().get("Buckets", []):
            name, item = bucket["Name"], dict(bucket)
            item["PublicAccessBlockConfiguration"] = self._pab(name); item["BucketEncryption"] = self._encryption(name); item["Tags"] = self._bucket_tags(name)
            if _matches(item["Tags"], scope): values.append(item)
        return values

    def _pab(self, bucket: str) -> dict[str, Any]:
        try: return self.s3_client.get_public_access_block(Bucket=bucket).get("PublicAccessBlockConfiguration", {})
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"NoSuchPublicAccessBlockConfiguration", "NoSuchBucket"}: return {}
            raise
    def _encryption(self, bucket: str) -> dict[str, Any]:
        try: return {"Rules": self.s3_client.get_bucket_encryption(Bucket=bucket).get("ServerSideEncryptionConfiguration", {}).get("Rules", [])}
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"ServerSideEncryptionConfigurationNotFoundError", "NoSuchBucket"}: return {"Rules": []}
            raise
    def _bucket_tags(self, bucket: str) -> list[dict[str, str]]:
        try: return self.s3_client.get_bucket_tagging(Bucket=bucket).get("TagSet", [])
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"NoSuchTagSet", "NoSuchBucket"}: return []
            raise

    def _roles(self, scope: dict[str, str]) -> list[dict[str, Any]]:
        roles: list[dict[str, Any]] = []
        for page in self.iam_client.get_paginator("list_roles").paginate():
            for listed in page.get("Roles", []):
                role = self.iam_client.get_role(RoleName=listed["RoleName"])["Role"]
                role["Tags"] = self._iam_tags("list_role_tags", RoleName=role["RoleName"])
                if not _matches(role["Tags"], scope):
                    if scope: self.diagnostics.append({"source": "aws_collection", "message": f"Excluded IAM role {role['RoleName']} because it does not match the active tag scope."})
                    continue
                role["ManagedPolicyArns"] = [x["PolicyArn"] for p in self.iam_client.get_paginator("list_attached_role_policies").paginate(RoleName=role["RoleName"]) for x in p.get("AttachedPolicies", [])]
                inline = []
                for p in self.iam_client.get_paginator("list_role_policies").paginate(RoleName=role["RoleName"]):
                    for name in p.get("PolicyNames", []):
                        policy = self.iam_client.get_role_policy(RoleName=role["RoleName"], PolicyName=name); inline.append({"name": name, "document": policy.get("PolicyDocument", {})})
                role["InlinePolicies"] = inline; roles.append(role)
        return roles

    def _profiles(self, scope: dict[str, str]) -> list[dict[str, Any]]:
        profiles: list[dict[str, Any]] = []
        for page in self.iam_client.get_paginator("list_instance_profiles").paginate():
            for listed in page.get("InstanceProfiles", []):
                profile = self.iam_client.get_instance_profile(InstanceProfileName=listed["InstanceProfileName"])["InstanceProfile"]
                profile["Tags"] = self._iam_tags("list_instance_profile_tags", InstanceProfileName=profile["InstanceProfileName"])
                if _matches(profile["Tags"], scope): profiles.append(profile)
                elif scope: self.diagnostics.append({"source": "aws_collection", "message": f"Excluded IAM instance profile {profile['InstanceProfileName']} because it does not match the active tag scope."})
        return profiles

    def _iam_tags(self, operation: str, **parameters: str) -> list[dict[str, str]]:
        return [tag for page in self.iam_client.get_paginator(operation).paginate(**parameters) for tag in page.get("Tags", [])]

    def _zones(self, scope: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        zones: list[dict[str, Any]] = []; records: dict[str, list[dict[str, Any]]] = {}
        for page in self.route53_client.get_paginator("list_hosted_zones").paginate():
            for zone in page.get("HostedZones", []):
                zone_id = zone["Id"]; resource_id = zone_id.rsplit("/", 1)[-1]
                zone = dict(zone); zone["Tags"] = self.route53_client.list_tags_for_resource(ResourceType="hostedzone", ResourceId=resource_id).get("ResourceTagSet", {}).get("Tags", [])
                if not _matches(zone["Tags"], scope): continue
                zones.append(zone); records[zone_id] = [record for p in self.route53_client.get_paginator("list_resource_record_sets").paginate(HostedZoneId=zone_id) for record in p.get("ResourceRecordSets", [])]
        return zones, records


def collect_live_inventory(profile: str | None, region: str, role_arn: str | None, tag_scope: dict[str, str] | None = None) -> dict[str, Any]:
    session = _session(profile, region, role_arn)
    return AwsInventoryCollector(session.client("ec2", region_name=region), session.client("s3", region_name=region), session.client("iam"), session.client("route53")).collect(tag_scope)


def _ec2_filters(scope: dict[str, str]) -> dict[str, list[dict[str, list[str]]]]: return {"Filters": [{"Name": f"tag:{key}", "Values": [value]} for key, value in sorted(scope.items())]} if scope else {}
def _matches(tags: list[dict[str, str]], scope: dict[str, str]) -> bool:
    values = {tag.get("Key"): tag.get("Value") for tag in tags}; return all(values.get(k) == v for k, v in scope.items())
def _session(profile: str | None, region: str, role_arn: str | None) -> boto3.Session:
    base = boto3.Session(profile_name=profile, region_name=region)
    if not role_arn: return base
    try: credentials = base.client("sts", region_name=region).assume_role(RoleArn=role_arn, RoleSessionName="driftctl-read-only")["Credentials"]
    except (BotoCoreError, ClientError) as error: raise AwsCollectionError(f"Unable to assume read-only role: {error}") from error
    return boto3.Session(aws_access_key_id=credentials["AccessKeyId"], aws_secret_access_key=credentials["SecretAccessKey"], aws_session_token=credentials["SessionToken"], region_name=region)
