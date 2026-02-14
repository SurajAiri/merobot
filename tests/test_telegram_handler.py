"""Unit tests for TelegramChannelHandler (all Telegram API calls are mocked).

The channel uses BaseChannelHandler._publish_inbound() to push messages
directly to the bus. No receive_message() or internal queue.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from merobot.handler.channels.telegram import TelegramChannelHandler
from merobot.handler.messages import OutboundMessage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_bus():
    """A lightweight mock that quacks like MessageBus."""
    bus = AsyncMock()
    bus.publish_inbound = AsyncMock()
    bus.subscribe_outbound = AsyncMock()
    return bus


@pytest.fixture
def handler(mock_bus):
    """A fresh TelegramChannelHandler wired to a mock bus."""
    return TelegramChannelHandler(bus=mock_bus, token="TEST_TOKEN_123")


# ---------------------------------------------------------------------------
# Helpers to build Telegram-like objects
# ---------------------------------------------------------------------------


def _make_telegram_update(text="hello", chat_id=42, user_id=7, message_id=1):
    """Create a minimal mock that looks like ``telegram.Update``."""
    user = MagicMock()
    user.id = user_id
    user.first_name = "Test"
    user.username = "testuser"

    chat = MagicMock()
    chat.type = "private"

    from datetime import datetime, timezone

    msg = MagicMock()
    msg.text = text
    msg.chat_id = chat_id
    msg.message_id = message_id
    msg.from_user = user
    msg.chat = chat
    msg.date = datetime.now(tz=timezone.utc)
    msg.photo = None
    msg.document = None
    msg.video = None
    msg.audio = None
    msg.voice = None

    update = MagicMock()
    update.message = msg
    return update


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConnect:
    """Verify the connect lifecycle."""

    @pytest.mark.asyncio
    @patch("merobot.handler.channels.telegram.Application")
    async def test_connect_starts_polling(self, MockApplication, handler):
        app_instance = AsyncMock()
        app_instance.bot = AsyncMock()
        app_instance.updater = AsyncMock()
        app_instance.updater.start_polling = AsyncMock()

        builder = MagicMock()
        builder.token.return_value = builder
        builder.build.return_value = app_instance
        MockApplication.builder.return_value = builder

        await handler.connect()

        builder.token.assert_called_once_with("TEST_TOKEN_123")
        app_instance.initialize.assert_awaited_once()
        app_instance.start.assert_awaited_once()
        app_instance.updater.start_polling.assert_awaited_once()
        assert handler._connected is True
        assert handler.is_running is True

    @pytest.mark.asyncio
    @patch("merobot.handler.channels.telegram.Application")
    async def test_double_connect_is_noop(self, MockApplication, handler):
        app_instance = AsyncMock()
        app_instance.bot = AsyncMock()
        app_instance.updater = AsyncMock()
        app_instance.updater.start_polling = AsyncMock()

        builder = MagicMock()
        builder.token.return_value = builder
        builder.build.return_value = app_instance
        MockApplication.builder.return_value = builder

        await handler.connect()
        await handler.connect()  # should be a no-op

        builder.build.assert_called_once()


class TestDisconnect:
    @pytest.mark.asyncio
    @patch("merobot.handler.channels.telegram.Application")
    async def test_disconnect_stops_app(self, MockApplication, handler):
        app_instance = AsyncMock()
        app_instance.bot = AsyncMock()
        app_instance.updater = AsyncMock()
        app_instance.updater.running = True
        app_instance.updater.start_polling = AsyncMock()

        builder = MagicMock()
        builder.token.return_value = builder
        builder.build.return_value = app_instance
        MockApplication.builder.return_value = builder

        await handler.connect()
        await handler.disconnect()

        app_instance.updater.stop.assert_awaited_once()
        app_instance.stop.assert_awaited_once()
        app_instance.shutdown.assert_awaited_once()
        assert handler._connected is False
        assert handler.is_running is False

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected_is_noop(self, handler):
        await handler.disconnect()


class TestSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_calls_bot(self, handler):
        handler._connected = True
        handler._bot = AsyncMock()

        outbound = OutboundMessage(
            channel="telegram",
            content="Hello from bot!",
            recipient_id="7",
            chat_id="42",
        )

        await handler.send_message(outbound)

        handler._bot.send_message.assert_awaited_once_with(
            chat_id="42",
            text="Hello from bot!",
        )

    @pytest.mark.asyncio
    async def test_send_message_raises_when_not_connected(self, handler):
        outbound = OutboundMessage(
            channel="telegram",
            content="oops",
            recipient_id="1",
            chat_id="1",
        )
        with pytest.raises(RuntimeError, match="not connected"):
            await handler.send_message(outbound)


class TestInboundPublishing:
    """Verify _handle_update publishes to bus via _publish_inbound."""

    @pytest.mark.asyncio
    async def test_handle_update_publishes_to_bus(self, handler, mock_bus):
        update = _make_telegram_update(text="hi bot", chat_id=42, user_id=7)
        context = MagicMock()

        await handler._handle_text(update, context)

        mock_bus.publish_inbound.assert_awaited_once()
        inbound = mock_bus.publish_inbound.call_args[0][0]
        assert inbound.channel == "telegram"
        assert inbound.content == "hi bot"
        assert inbound.sender_id == "7"
        assert inbound.chat_id == "42"
        assert inbound.metadata["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_handle_update_ignores_none_message(self, handler, mock_bus):
        update = MagicMock()
        update.message = None
        context = MagicMock()

        await handler._handle_text(update, context)

        mock_bus.publish_inbound.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handle_update_ignores_none_text(self, handler, mock_bus):
        update = MagicMock()
        update.message = MagicMock()
        update.message.text = None
        context = MagicMock()

        await handler._handle_text(update, context)

        mock_bus.publish_inbound.assert_not_awaited()


class TestTyping:
    @pytest.mark.asyncio
    async def test_start_typing_sends_action(self, handler):
        handler._connected = True
        handler._bot = AsyncMock()

        await handler.start_typing("42")

        handler._bot.send_chat_action.assert_awaited_once()
        call_kwargs = handler._bot.send_chat_action.call_args[1]
        assert call_kwargs["chat_id"] == "42"

    @pytest.mark.asyncio
    async def test_stop_typing_is_noop(self, handler):
        await handler.stop_typing("42")

    @pytest.mark.asyncio
    async def test_start_typing_raises_when_not_connected(self, handler):
        with pytest.raises(RuntimeError, match="not connected"):
            await handler.start_typing("42")


class TestMediaExtraction:
    def test_extracts_photo(self):
        msg = MagicMock()
        photo_large = MagicMock()
        photo_large.file_id = "photo_123"
        msg.photo = [MagicMock(), photo_large]
        msg.document = None
        msg.video = None
        msg.audio = None
        msg.voice = None

        result = TelegramChannelHandler._extract_media(msg)
        assert result == ["photo_123"]

    def test_extracts_document(self):
        msg = MagicMock()
        msg.photo = None
        msg.document = MagicMock()
        msg.document.file_id = "doc_456"
        msg.video = None
        msg.audio = None
        msg.voice = None

        result = TelegramChannelHandler._extract_media(msg)
        assert result == ["doc_456"]

    def test_no_media_returns_empty(self):
        msg = MagicMock()
        msg.photo = None
        msg.document = None
        msg.video = None
        msg.audio = None
        msg.voice = None

        result = TelegramChannelHandler._extract_media(msg)
        assert result == []
