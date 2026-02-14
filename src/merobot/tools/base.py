"""Base class for agent tools."""

from abc import ABC, abstractmethod
from typing import Any

from jsonschema import Draft7Validator


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

    def validate_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Validate parameters against this tool's JSON Schema.

        Returns:
            dict with 'valid' (bool) and 'errors' (list[str] | None).
        """
        try:
            validator = Draft7Validator(self.parameters)
        except Exception as e:
            return {"valid": False, "errors": [f"Invalid tool schema: {e}"]}

        errors = sorted(validator.iter_errors(params), key=lambda e: list(e.path))

        if errors:
            formatted = []
            for error in errors:
                field = ".".join(str(p) for p in error.path) or "root"
                formatted.append(f"[{field}] {error.message}")
            return {"valid": False, "errors": formatted}

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
