from loguru import logger

from merobot.agents import ToolRegistry
from merobot.config import AgentConfig, AgentDefaults, get_config
from merobot.handler.message_bus import MessageBus
from merobot.providers.llm import LiteLLMProvider
from merobot.tools import (
    DateTimeTool,
    FileReadTool,
    FileWriteTool,
    WebScrapeTool,
    WebSearchTool,
)


class AgentLoop:
    def __init__(self):
        self.config = get_config()
        self.message_bus: MessageBus = MessageBus()
        self.model_config = self.config.agent.defaults
        api_token = self.config.providers[self.model_config.provider].api_key
        self.llm = LiteLLMProvider(api_token)

        self._register_tools()

    def _register_tools(self):
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(DateTimeTool())
        self.tool_registry.register(FileReadTool())
        self.tool_registry.register(FileWriteTool())
        self.tool_registry.register(WebScrapeTool())
        self.tool_registry.register(WebSearchTool())

    def run(self):
        pass
