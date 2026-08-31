import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError


@dataclass(frozen=True)
class StructuredValidationResult:
    valid: bool
    data: BaseModel | None = None
    errors: list[str] = field(default_factory=list)
    attempts: int = 0
    repaired: bool = False


def json_schema_for(model: type[BaseModel]) -> dict[str, Any]:
    return model.model_json_schema()


def validate_structured_output(
    payload: Any,
    model: type[BaseModel],
    max_retries: int = 1,
    repair_fn=None,
) -> StructuredValidationResult:
    attempts = 0
    current_payload = payload
    errors: list[str] = []
    repaired = False

    while attempts <= max_retries:
        attempts += 1
        try:
            value = _coerce_payload(current_payload)
            data = model.model_validate(value)
            return StructuredValidationResult(
                valid=True,
                data=data,
                attempts=attempts,
                repaired=repaired,
            )
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            errors = _format_errors(exc)
            if attempts > max_retries:
                break
            current_payload = repair_fn(current_payload, errors) if repair_fn else default_repair(current_payload)
            repaired = True

    return StructuredValidationResult(
        valid=False,
        errors=errors,
        attempts=attempts,
        repaired=repaired,
    )


def default_repair(payload: Any) -> Any:
    if isinstance(payload, str):
        extracted = _extract_json_object(payload)
        if extracted is not None:
            return extracted
    return payload


def _coerce_payload(payload: Any) -> Any:
    if isinstance(payload, BaseModel):
        return payload.model_dump()
    if isinstance(payload, str):
        return json.loads(payload)
    return payload


def _extract_json_object(text: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    return json.loads(match.group(0))


def _format_errors(exc: Exception) -> list[str]:
    if isinstance(exc, ValidationError):
        return [f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()]
    return [str(exc)]
