"""Shared canonicalization for Terraform and boto3 serverless shapes."""

from __future__ import annotations

from typing import Any


def lambda_configuration(values: dict[str, Any]) -> dict[str, Any]:
    environment = _first(values.get("environment", values.get("Environment")))
    tracing = _first(values.get("tracing_config", values.get("TracingConfig")))
    ephemeral = _first(values.get("ephemeral_storage", values.get("EphemeralStorage")))
    vpc = _first(values.get("vpc_config", values.get("VpcConfig")))
    dead_letter = _first(values.get("dead_letter_config", values.get("DeadLetterConfig")))
    concurrency = values.get(
        "reserved_concurrent_executions",
        values.get("ReservedConcurrentExecutions", -1),
    )
    return {
        "runtime": values.get("runtime", values.get("Runtime")),
        "handler": _none_if_blank(values.get("handler", values.get("Handler"))),
        "role_arn": values.get("role", values.get("Role")),
        "memory_size": values.get("memory_size", values.get("MemorySize", 128)),
        "timeout": values.get("timeout", values.get("Timeout", 3)),
        "package_type": values.get("package_type", values.get("PackageType", "Zip")),
        "architectures": sorted(
            values.get("architectures", values.get("Architectures", ["x86_64"]))
        ),
        "reserved_concurrent_executions": -1 if concurrency is None else concurrency,
        "environment": dict(
            sorted(environment.get("variables", environment.get("Variables", {})).items())
        ),
        "tracing_mode": tracing.get("mode", tracing.get("Mode", "PassThrough")),
        "ephemeral_storage_gib": ephemeral.get("size", ephemeral.get("Size", 512)),
        "vpc_config": {
            "subnet_ids": sorted(vpc.get("subnet_ids", vpc.get("SubnetIds", []))),
            "security_group_ids": sorted(
                vpc.get("security_group_ids", vpc.get("SecurityGroupIds", []))
            ),
        },
        "dead_letter_target_arn": _none_if_blank(
            dead_letter.get("target_arn", dead_letter.get("TargetArn"))
        ),
        "layers": sorted(_layer_arns(values.get("layers", values.get("Layers", [])))),
        "kms_key_arn": _none_if_blank(values.get("kms_key_arn", values.get("KMSKeyArn"))),
        "description": _none_if_blank(values.get("description", values.get("Description"))),
    }


def eventbridge_rule_configuration(
    values: dict[str, Any],
    targets: Any,
) -> dict[str, Any]:
    state = values.get("state", values.get("State"))
    if state is None:
        enabled = bool(values.get("is_enabled", True))
    else:
        enabled = str(state).upper() != "DISABLED"
    return {
        "schedule_expression": _none_if_blank(
            values.get("schedule_expression", values.get("ScheduleExpression"))
        ),
        "enabled": enabled,
        "description": _none_if_blank(values.get("description", values.get("Description"))),
        "event_bus_name": (
            values.get("event_bus_name", values.get("EventBusName")) or "default"
        ),
        "role_arn": _none_if_blank(values.get("role_arn", values.get("RoleArn"))),
        "targets": eventbridge_targets(targets),
    }


def eventbridge_targets(values: Any) -> list[dict[str, Any]]:
    normalized = []
    for value in values or []:
        transformer = _first(value.get("input_transformer", value.get("InputTransformer")))
        retry = _first(value.get("retry_policy", value.get("RetryPolicy")))
        dead_letter = _first(
            value.get("dead_letter_config", value.get("DeadLetterConfig"))
        )
        normalized.append({
            "id": value.get("target_id", value.get("Id")),
            "arn": value.get("arn", value.get("Arn")),
            "role_arn": _none_if_blank(value.get("role_arn", value.get("RoleArn"))),
            "input": _none_if_blank(value.get("input", value.get("Input"))),
            "input_path": _none_if_blank(
                value.get("input_path", value.get("InputPath"))
            ),
            "input_transformer": {
                "input_paths": dict(
                    sorted(
                        transformer.get(
                            "input_paths",
                            transformer.get("InputPathsMap", {}),
                        ).items()
                    )
                ),
                "input_template": _none_if_blank(
                    transformer.get(
                        "input_template",
                        transformer.get("InputTemplate"),
                    )
                ),
            },
            "retry_policy": {
                "maximum_event_age_in_seconds": retry.get(
                    "maximum_event_age_in_seconds",
                    retry.get("MaximumEventAgeInSeconds", 86400),
                ),
                "maximum_retry_attempts": retry.get(
                    "maximum_retry_attempts",
                    retry.get("MaximumRetryAttempts", 185),
                ),
            },
            "dead_letter_arn": _none_if_blank(
                dead_letter.get("arn", dead_letter.get("Arn"))
            ),
        })
    return sorted(normalized, key=lambda item: (item["id"] or "", item["arn"] or ""))


def _layer_arns(values: Any) -> list[str]:
    return [
        value.get("Arn")
        if isinstance(value, dict)
        else str(value)
        for value in values or []
        if (isinstance(value, dict) and value.get("Arn")) or not isinstance(value, dict)
    ]


def _first(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return value[0] if value else {}
    return value if isinstance(value, dict) else {}


def _none_if_blank(value: Any) -> Any:
    return None if value in (None, "") else value
