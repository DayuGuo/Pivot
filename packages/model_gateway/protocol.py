"""Shared schema/telemetry protocol; no publishing authority."""

import math

from .editorial import safe_error_code


def sanitized_telemetry(metric):
    """Provider/body-defined strings never become diagnostic fields."""
    provider = getattr(metric, "provider", None)
    models = {"deepseek": "deepseek-flash", "mock": "contextual-simulator-v1"}
    provider = provider if type(provider) is str and provider in models else "unavailable"

    def counter(name, default=None):
        value = getattr(metric, name, None)
        return value if type(value) is int and 0 <= value <= 10**12 else default

    success = getattr(metric, "success", None) is True
    cost = getattr(metric, "cost_usd", None)
    return {
        "provider": provider,
        "model": models.get(provider, "unknown"),
        "success": success,
        "duration_ms": counter("duration_ms"),
        "input_tokens": counter("input_tokens"),
        "output_tokens": counter("output_tokens"),
        "cost_usd": cost
        if type(cost) in {int, float} and 0 <= cost <= 10**6 and math.isfinite(cost)
        else None,
        "cost_basis": "unknown; reconcile provider invoice",
        "rework_count": counter("rework_count", 0),
        "error_code": None if success else safe_error_code(getattr(metric, "error_code", None)),
    }


def tool_schema(model):
    """Inline bounded local DTO references for portable function-schema transport."""
    schema = model.model_json_schema()
    definitions = schema.pop("$defs", {})

    def expand(value):
        if isinstance(value, list):
            return [expand(item) for item in value]
        if isinstance(value, dict):
            if "$ref" in value:
                reference = value["$ref"]
                return expand(definitions[reference.removeprefix("#/$defs/")])
            return {key: expand(item) for key, item in value.items() if key != "$defs"}
        return value

    return expand(schema)
