from typing import Any

from merobot.tools.base import BaseTool


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    @property
    def tool_names(self):
        """List of registered tool names."""
        return list(self._tools.keys())

    def register(self, tool: BaseTool):
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered.")
        self._tools[tool.name] = tool

    def unregister(self, name: str):
        if name in self._tools:
            del self._tools[name]

    def get_tool(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_definitions(self) -> list[dict]:
        """Get list of tool definitions for LLM function calls."""
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any]) -> str:
        tool = self.get_tool(name)
        if not tool:
            return f"Error: Tool '{name}' not found."

        try:
            validation = tool.validate_params(params)
            if not validation["valid"]:
                return (
                    f"Error: Invalid params for tool '{name}': {validation['errors']}"
                )
            return await tool.execute(**params)
        except Exception as e:
            return f"Error: executing '{name}': {type(e).__name__}: {e}"

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)
