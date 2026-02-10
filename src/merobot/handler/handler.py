# roles: connection with channels, message transport, session with message history management. # noqa:E501
from merobot.handler.channels.telegram import TelegramChannelHandler
from merobot.handler.message_bus import MessageBus
import os

class CommunicationHandler:
    def __init__(self, config: dict):
        self.config = config
        self.message_bus = MessageBus()
        self.channels = []
        self.sessions = {}

        self._register_valid_channels()

    def _register_valid_channels(self):
        for channel in self.config["channels"]:
            if not channel['enabled']:
                continue
            
            channel_type = channel['type']
            token = os.getenv(channel['env_token'])
            if channel_type == 'telegram':
                self.channels.append(TelegramChannelHandler(token, self.message_bus))
                self.message_bus.subscribe_outbound(channel_type, self.channels[-1].send_message)   
            # elif channel_type == 'whatsapp':
            #     self.channels.append(WhatsappChannelHandler(channel['token'], self.message_bus))
            else:
                logger.warning(f"Unknown channel type: {channel_type}")

    async def start(self):
        for channel in self.channels:
            await channel.connect()

    async def stop(self):
        for channel in self.channels:
            await channel.disconnect()