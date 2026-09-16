"""Read-only AWS inventory collector; no mutation API is called."""

from __future__ import annotations

from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError


class AwsCollectionError(RuntimeError): pass


class AwsInventoryCollector:
    def __init__(
        self,
        ec2_client: Any,
        s3_client: Any,
        iam_client: Any | None = None,
        route53_client: Any | None = None,
        elbv2_client: Any | None = None,
        rds_client: Any | None = None,
        ecs_client: Any | None = None,
        logs_client: Any | None = None,
    ) -> None:
        self.ec2_client, self.s3_client, self.iam_client, self.route53_client = ec2_client, s3_client, iam_client, route53_client
        self.elbv2_client, self.rds_client = elbv2_client, rds_client
        self.ecs_client, self.logs_client = ecs_client, logs_client
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
                "NatGateways": self._ec2("describe_nat_gateways", "NatGateways", scope),
                "IamRoles": self._roles(scope) if self.iam_client else [],
                "InstanceProfiles": self._profiles(scope) if self.iam_client else [],
                "HostedZones": [], "RecordSets": {}, "LoadBalancers": [], "TargetGroups": [], "TargetGroupReferences": {},
                "Listeners": {}, "ListenerRules": {},
                "DBInstances": self._db_instances(scope) if self.rds_client else [],
                "ECSClusters": [], "ECSTaskDefinitions": [], "ECSServices": [],
                "LogGroups": self._log_groups(scope) if self.logs_client else [],
                "CollectionDiagnostics": self.diagnostics,
            }
            if self.route53_client: inventory["HostedZones"], inventory["RecordSets"] = self._zones(scope)
            if self.elbv2_client: inventory.update(self._load_balancing(scope))
            if self.ecs_client: inventory.update(self._ecs(scope))
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

    def _load_balancing(self, scope: dict[str, str]) -> dict[str, Any]:
        load_balancers = self._elb_tagged("describe_load_balancers", "LoadBalancers", scope)
        all_target_groups = self._elb_tagged("describe_target_groups", "TargetGroups", {})
        target_groups = [item for item in all_target_groups if _matches(item.get("Tags", []), scope)]
        listeners: dict[str, list[dict[str, Any]]] = {}
        rules: dict[str, list[dict[str, Any]]] = {}
        for load_balancer in load_balancers:
            arn = load_balancer["LoadBalancerArn"]
            listener_values = [item for page in self.elbv2_client.get_paginator("describe_listeners").paginate(LoadBalancerArn=arn) for item in page.get("Listeners", [])]
            for listener in listener_values:
                listener["Tags"] = load_balancer.get("Tags", [])
                listener_arn = listener["ListenerArn"]
                rules[listener_arn] = [item for page in self.elbv2_client.get_paginator("describe_rules").paginate(ListenerArn=listener_arn) for item in page.get("Rules", [])]
                for rule in rules[listener_arn]: rule["Tags"] = load_balancer.get("Tags", [])
            listeners[arn] = listener_values
        references = {item["TargetGroupArn"]: _tag_name(item.get("Tags", [])) or item.get("TargetGroupName") for item in all_target_groups}
        return {"LoadBalancers": load_balancers, "TargetGroups": target_groups, "TargetGroupReferences": references, "Listeners": listeners, "ListenerRules": rules}

    def _elb_tagged(self, operation: str, result_key: str, scope: dict[str, str]) -> list[dict[str, Any]]:
        values = [item for page in self.elbv2_client.get_paginator(operation).paginate() for item in page.get(result_key, [])]
        arn_key = "LoadBalancerArn" if result_key == "LoadBalancers" else "TargetGroupArn"
        tags_by_arn: dict[str, list[dict[str, str]]] = {}
        for start in range(0, len(values), 20):
            arns = [value[arn_key] for value in values[start:start + 20]]
            for item in self.elbv2_client.describe_tags(ResourceArns=arns).get("TagDescriptions", []): tags_by_arn[item["ResourceArn"]] = item.get("Tags", [])
        for value in values: value["Tags"] = tags_by_arn.get(value[arn_key], [])
        return [value for value in values if _matches(value["Tags"], scope)]

    def _db_instances(self, scope: dict[str, str]) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        for page in self.rds_client.get_paginator("describe_db_instances").paginate():
            for instance in page.get("DBInstances", []):
                item = dict(instance)
                item["Tags"] = self.rds_client.list_tags_for_resource(ResourceName=item["DBInstanceArn"]).get("TagList", [])
                if _matches(item["Tags"], scope): values.append(item)
        return values

    def _ecs(self, scope: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
        cluster_arns = [
            arn
            for page in self.ecs_client.get_paginator("list_clusters").paginate()
            for arn in page.get("clusterArns", [])
        ]
        all_clusters: list[dict[str, Any]] = []
        for start in range(0, len(cluster_arns), 100):
            response = self.ecs_client.describe_clusters(
                clusters=cluster_arns[start:start + 100], include=["TAGS", "SETTINGS"]
            )
            all_clusters.extend(response.get("clusters", []))
        cluster_by_arn = {cluster["clusterArn"]: cluster for cluster in all_clusters}
        clusters = [cluster for cluster in all_clusters if _matches(_ecs_tags(cluster), scope)]

        services: list[dict[str, Any]] = []
        inherited_task_tags: dict[str, list[dict[str, str]]] = {}
        for cluster_arn in cluster_arns:
            service_arns = [
                arn
                for page in self.ecs_client.get_paginator("list_services").paginate(cluster=cluster_arn)
                for arn in page.get("serviceArns", [])
            ]
            for start in range(0, len(service_arns), 10):
                response = self.ecs_client.describe_services(
                    cluster=cluster_arn,
                    services=service_arns[start:start + 10],
                    include=["TAGS"],
                )
                for service in response.get("services", []):
                    own_tags = _ecs_tags(service)
                    effective_tags = own_tags or _ecs_tags(cluster_by_arn.get(cluster_arn, {}))
                    if not _matches(effective_tags, scope):
                        continue
                    item = dict(service)
                    item["tags"] = effective_tags
                    services.append(item)
                    if item.get("taskDefinition"):
                        inherited_task_tags[item["taskDefinition"]] = effective_tags
                        inherited_task_tags[_task_definition_family(item["taskDefinition"])] = effective_tags

        active_definition_arns = [
            arn
            for page in self.ecs_client.get_paginator("list_task_definitions").paginate(status="ACTIVE")
            for arn in page.get("taskDefinitionArns", [])
        ]
        definition_arns = _task_definition_arns_for_comparison(
            active_definition_arns,
            {service["taskDefinition"] for service in services if service.get("taskDefinition")},
        )
        task_definitions: list[dict[str, Any]] = []
        for arn in definition_arns:
            response = self.ecs_client.describe_task_definition(taskDefinition=arn, include=["TAGS"])
            definition = dict(response["taskDefinition"])
            own_tags = _ecs_tags(response)
            family = _task_definition_family(arn)
            effective_tags = own_tags or inherited_task_tags.get(arn, []) or inherited_task_tags.get(family, [])
            if _matches(effective_tags, scope):
                definition["tags"] = effective_tags
                task_definitions.append(definition)
        return {"ECSClusters": clusters, "ECSTaskDefinitions": task_definitions, "ECSServices": services}

    def _log_groups(self, scope: dict[str, str]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for page in self.logs_client.get_paginator("describe_log_groups").paginate():
            for group in page.get("logGroups", []):
                item = dict(group)
                arn = item.get("logGroupArn") or str(item.get("arn", "")).removesuffix(":*")
                item["tags"] = self.logs_client.list_tags_for_resource(resourceArn=arn).get("tags", {})
                if _matches(item["tags"], scope):
                    groups.append(item)
        return groups


def collect_live_inventory(profile: str | None, region: str, role_arn: str | None, tag_scope: dict[str, str] | None = None) -> dict[str, Any]:
    session = _session(profile, region, role_arn)
    return AwsInventoryCollector(
        session.client("ec2", region_name=region),
        session.client("s3", region_name=region),
        session.client("iam"),
        session.client("route53"),
        session.client("elbv2", region_name=region),
        session.client("rds", region_name=region),
        session.client("ecs", region_name=region),
        session.client("logs", region_name=region),
    ).collect(tag_scope)


def _ec2_filters(scope: dict[str, str]) -> dict[str, list[dict[str, list[str]]]]: return {"Filters": [{"Name": f"tag:{key}", "Values": [value]} for key, value in sorted(scope.items())]} if scope else {}
def _matches(tags: list[dict[str, str]] | dict[str, str], scope: dict[str, str]) -> bool:
    values = tags if isinstance(tags, dict) else {
        tag.get("Key") or tag.get("key"): tag.get("Value", tag.get("value")) for tag in tags
    }
    return all(values.get(k) == v for k, v in scope.items())
def _ecs_tags(value: dict[str, Any]) -> list[dict[str, str]]:
    return value.get("tags", value.get("Tags", []))
def _task_definition_family(arn: str) -> str:
    return arn.rsplit("/", 1)[-1].rsplit(":", 1)[0]
def _task_definition_arns_for_comparison(arns: list[str], referenced_arns: set[str]) -> list[str]:
    latest: dict[str, tuple[int, str]] = {}
    for arn in arns:
        family_revision = arn.rsplit("/", 1)[-1]
        family, separator, revision = family_revision.rpartition(":")
        if not separator or not revision.isdigit():
            continue
        candidate = (int(revision), arn)
        if family not in latest or candidate[0] > latest[family][0]:
            latest[family] = candidate
    referenced_families = {_task_definition_family(arn) for arn in referenced_arns}
    selected = set(referenced_arns)
    selected.update(item[1] for family, item in latest.items() if family not in referenced_families)
    return sorted(selected)
def _tag_name(tags: list[dict[str, str]]) -> str | None: return next((tag.get("Value") for tag in tags if tag.get("Key") == "Name"), None)
def _session(profile: str | None, region: str, role_arn: str | None) -> boto3.Session:
    base = boto3.Session(profile_name=profile, region_name=region)
    if not role_arn: return base
    try: credentials = base.client("sts", region_name=region).assume_role(RoleArn=role_arn, RoleSessionName="driftctl-read-only")["Credentials"]
    except (BotoCoreError, ClientError) as error: raise AwsCollectionError(f"Unable to assume read-only role: {error}") from error
    return boto3.Session(aws_access_key_id=credentials["AccessKeyId"], aws_secret_access_key=credentials["SecretAccessKey"], aws_session_token=credentials["SessionToken"], region_name=region)
