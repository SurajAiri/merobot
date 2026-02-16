"""Base class for agent tools."""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """
    Abstract base class for agent tools.

    Tools are capabilities that the agent can use to interact with
    the environment, such as reading files, executing commands,
    searching the web, etc.

    Subclasses must implement: name, description, parameters, execute.
    Validation uses JSON Schema Draft 7 via the jsonschema library.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name used in LLM function calls (e.g. 'web_search')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what the tool does."""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """
        JSON Schema (Draft 7) defining the tool's accepted parameters.

        Must have `"type": "object"` at the top level with `properties`
        and optionally `required`.
        """
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """
        Execute the tool with the given parameters.

        Args:
            **kwargs: Tool-specific parameters matching the schema.

        Returns:
            String result of the tool execution. Tools should never
            raise exceptions — return descriptive error strings instead.
        """
        ...

    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    def _validate_params(self, params: dict[str, Any]) -> list[str]:
        """Validate tool parameters against JSON schema. Returns error list (empty if valid)."""
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: dict[str, Any], path: str) -> list[str]:
        t, label = schema.get("type"), path or "parameter"
        if t in self._TYPE_MAP and not isinstance(val, self._TYPE_MAP[t]):
            return [f"{label} should be {t}"]

        errors = []
        if "enum" in schema and val not in schema["enum"]:
            errors.append(f"{label} must be one of {schema['enum']}")
        if t in ("integer", "number"):
            if "minimum" in schema and val < schema["minimum"]:
                errors.append(f"{label} must be >= {schema['minimum']}")
            if "maximum" in schema and val > schema["maximum"]:
                errors.append(f"{label} must be <= {schema['maximum']}")
        if t == "string":
            if "minLength" in schema and len(val) < schema["minLength"]:
                errors.append(f"{label} must be at least {schema['minLength']} chars")
            if "maxLength" in schema and len(val) > schema["maxLength"]:
                errors.append(f"{label} must be at most {schema['maxLength']} chars")
        if t == "object":
            props = schema.get("properties", {})
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"missing required {path + '.' + k if path else k}")
            for k, v in val.items():
                if k in props:
                    errors.extend(
                        self._validate(v, props[k], path + "." + k if path else k)
                    )
        if t == "array" and "items" in schema:
            for i, item in enumerate(val):
                errors.extend(
                    self._validate(
                        item, schema["items"], f"{path}[{i}]" if path else f"[{i}]"
                    )
                )
        return errors

    def validate_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Validate parameters against this tool's JSON Schema.

        Returns:
            dict with 'valid' (bool) and 'errors' (list[str] | None).
        """
        errors = self._validate_params(params)
        if errors:
            return {"valid": False, "errors": errors}

        return {"valid": True, "errors": None}

    def to_schema(self) -> dict[str, Any]:
        """Convert tool to OpenAI-compatible function calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
