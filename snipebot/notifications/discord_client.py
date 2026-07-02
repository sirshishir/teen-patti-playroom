"""
discord_client.py — Persistent discord.py bot (gateway) for SnipeBot.

Runs a discord.py Bot in a background thread with its own asyncio event loop
so it can coexist with the synchronous APScheduler in main.py.

Responsibilities:
  • Maintain a live gateway connection.
  • Post all bot messages into a single channel (default: #price-alert).
  • Listen for the "Show Analysis" command (slash command /analysis and the
    plain-text phrase "show analysis") and reply with the current SMC analysis.

Thread-safety:
  The rest of the codebase is synchronous and runs in APScheduler threads.
  post() marshals the coroutine onto the bot's event loop via
  asyncio.run_coroutine_threadsafe(), which is safe from any thread.

Configuration (env vars):
  DISCORD_BOT_TOKEN    — bot token from the Discord Developer Portal (required)
  DISCORD_CHANNEL_NAME — target channel name without '#' (default: price-alert)
  DISCORD_CHANNEL_ID   — optional explicit channel ID (overrides name lookup)
"""

import asyncio
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_LEN = 2000  # Discord hard limit per message

# Runtime state (populated once the bot connects)
_bot = None
_loop: Optional[asyncio.AbstractEventLoop] = None
_channel = None
_thread: Optional[threading.Thread] = None
_ready = threading.Event()
_started = False

_CHANNEL_NAME = os.getenv("DISCORD_CHANNEL_NAME", "price-alert").lstrip("#")
_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "").strip()


def is_running() -> bool:
    """True once the gateway is connected and the target channel is resolved."""
    return _ready.is_set() and _channel is not None


def wait_until_ready(timeout: float = 30.0) -> bool:
    """Block until the bot has connected and resolved its channel."""
    return _ready.wait(timeout=timeout)


def _resolve_channel(bot):
    """Find the target channel by explicit ID, then by name."""
    if _CHANNEL_ID:
        try:
            ch = bot.get_channel(int(_CHANNEL_ID))
            if ch is not None:
                return ch
        except ValueError:
            logger.warning("DISCORD_CHANNEL_ID %r is not a valid integer", _CHANNEL_ID)
    import discord
    return discord.utils.get(bot.get_all_channels(), name=_CHANNEL_NAME)


def _build_analysis_text() -> str:
    """
    Assemble the current SMC analysis report (blocking — does network I/O).
    Imported lazily to avoid a circular import (scanner → discord_bot →
    discord_client).
    """
    try:
        from reports.analysis_snapshot import build_analysis_report
        return build_analysis_report()
    except Exception as exc:  # never let a command crash the gateway
        logger.error("Failed to build analysis report: %s", exc)
        return f"⚠️ Could not build analysis: {exc}"


def start_bot(token: Optional[str] = None) -> bool:
    """
    Launch the discord.py bot in a daemon background thread.
    Returns True if a start was initiated, False if no token is configured
    or the bot is already running.
    """
    global _bot, _thread, _started

    if _started:
        logger.debug("Discord bot already started")
        return True

    token = token or os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        logger.info("DISCORD_BOT_TOKEN not set — gateway bot disabled "
                    "(will fall back to webhook if configured)")
        return False

    import discord
    from discord.ext import commands

    intents = discord.Intents.default()
    # message_content is a privileged intent — required for the plain-text
    # "show analysis" trigger. Must also be enabled in the Developer Portal.
    intents.message_content = True

    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

    @bot.event
    async def on_ready():
        global _channel
        _channel = _resolve_channel(bot)
        if _channel is None:
            logger.error("Channel #%s not found — check the bot is in the "
                         "server and the channel name/ID is correct", _CHANNEL_NAME)
        else:
            logger.info("Discord bot connected as %s — posting to #%s",
                        bot.user, getattr(_channel, "name", _CHANNEL_NAME))
        # Sync slash commands to each guild for instant availability
        try:
            for guild in bot.guilds:
                bot.tree.copy_global_to(guild=guild)
                await bot.tree.sync(guild=guild)
        except Exception as exc:
            logger.warning("Slash command sync failed: %s", exc)
        _ready.set()

    @bot.tree.command(name="analysis",
                      description="Show SnipeBot's current SMC analysis")
    async def analysis_cmd(interaction):
        # Only respond in the designated channel
        if _channel is not None and interaction.channel_id != _channel.id:
            await interaction.response.send_message(
                f"Please use this command in #{_CHANNEL_NAME}.", ephemeral=True)
            return
        await interaction.response.defer()
        text = await asyncio.to_thread(_build_analysis_text)
        await interaction.followup.send(text[:_MAX_LEN])

    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return
        in_target = _channel is not None and message.channel.id == _channel.id
        if in_target and "show analysis" in message.content.lower():
            async with message.channel.typing():
                text = await asyncio.to_thread(_build_analysis_text)
            await message.channel.send(text[:_MAX_LEN])
        await bot.process_commands(message)

    def _run():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            _loop.run_until_complete(bot.start(token))
        except Exception as exc:
            logger.error("Discord gateway stopped: %s", exc)

    _bot = bot
    _thread = threading.Thread(target=_run, name="discord-gateway", daemon=True)
    _thread.start()
    _started = True
    logger.info("Discord gateway bot thread started")
    return True


def post(content: str) -> bool:
    """
    Send *content* to the target channel from any thread. Returns True on
    success. No-op (False) if the gateway isn't connected yet.
    """
    if _loop is None or _channel is None:
        return False
    try:
        coro = _channel.send(content[:_MAX_LEN])
        fut = asyncio.run_coroutine_threadsafe(coro, _loop)
        fut.result(timeout=10)
        return True
    except Exception as exc:
        logger.error("Discord gateway post failed: %s", exc)
        return False
