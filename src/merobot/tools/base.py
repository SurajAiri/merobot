from abc import ABC, abstractmethod


class BaseTool(ABC):
    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the tool"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of the tool for LLM to understand when to use it"""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON Schema of the parameters required to call the tool"""
        pass

    @abstractmethod
    async def execute(self, **kwargs):
        """Execute the tool with given parameters and return the result"""
        pass

    def to_schema(self):
        """Convert tool to openai function calling schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    # todo: make this validation more robust enough to handle all edge cases with proper error messages
    def validate_params(self, params: dict):
        """Validate parameters against the JSON schema"""
        schema = self.parameters
        for prop, details in schema["properties"].items():
            if prop in params:
                expected_type = self._TYPE_MAP[details["type"]]
                if not isinstance(params[prop], expected_type):
                    raise ValueError(
                        f"Parameter '{prop}' should be of type {details['type']}"
                    )
            elif prop in schema.get("required", []):
                raise ValueError(f"Missing required parameter: '{prop}'")
