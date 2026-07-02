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
  DISCORD_BOT_TOKEN          — bot token from the Developer Portal (required)
  DISCORD_CHANNEL_NAME       — target channel name without '#' (default: price-alert)
  DISCORD_CHANNEL_ID         — optional explicit channel ID (overrides name lookup)
  DISCORD_ENABLE_TEXT_COMMAND — 'true' to enable the plain-text "show analysis"
                                trigger. This needs the Message Content
                                privileged intent enabled in the Developer
                                Portal; if it's not, Discord refuses the
                                connection. Default 'false' — the /analysis
                                slash command works either way.
"""

import asyncio
import logging
import os
import threading
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

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
    return discord.utils.get(bot.get_all_channels(), name=_CHANNEL_NAME)


def _build_analysis_text(tickers=None) -> str:
    """
    Assemble the current (fresh) SMC analysis report (blocking — does network
    I/O). Imported lazily to avoid a circular import (scanner → discord_bot →
    discord_client). If *tickers* is given, analyses just those.
    """
    try:
        from reports.analysis_snapshot import build_analysis_report
        return build_analysis_report(tickers=tickers)
    except Exception as exc:  # never let a command crash the gateway
        logger.error("Failed to build analysis report: %s", exc)
        return f"⚠️ Could not build analysis: {exc}"


def _add_ticker_text(ticker: str) -> str:
    """Validate and add *ticker* to the watchlist. Returns a status message."""
    from data import database as db
    from data.market_data import fetch_ohlcv

    ticker = ticker.strip().upper()
    if not ticker or not ticker.isalnum():
        return f"⚠️ '{ticker}' is not a valid ticker symbol."
    try:
        df = fetch_ohlcv(ticker, interval="1Day", period_days=5)
        if df is None or df.empty:
            return f"⚠️ Couldn't fetch data for {ticker} — not added. Check the symbol."
        if db.add_to_watchlist(ticker):
            return (f"✅ Added **{ticker}** to the watchlist. It will be scanned "
                    f"every 30 min and included in /analysis.")
        return f"ℹ️ {ticker} is already on the watchlist."
    except Exception as exc:
        logger.error("add ticker error for %s: %s", ticker, exc)
        return f"⚠️ Could not add {ticker}: {exc}"


def _remove_ticker_text(ticker: str) -> str:
    """Remove *ticker* from the watchlist. Returns a status message."""
    from data import database as db
    ticker = ticker.strip().upper()
    if db.remove_from_watchlist(ticker):
        return f"✅ Removed **{ticker}** from the watchlist."
    return f"ℹ️ {ticker} wasn't on the watchlist."


def _config_text(ticker: Optional[str], value: int) -> str:
    """Set the global or per-ticker near-miss alert threshold."""
    from data import database as db
    if not (1 <= value <= 12):
        return "⚠️ Threshold must be between 1 and 12."
    if ticker:
        ticker = ticker.strip().upper()
        db.set_ticker_near_miss_threshold(ticker, value)
        return (f"✅ {ticker} alert threshold set to **{value}/12** — you'll get a "
                f"near-miss alert for {ticker} at {value} or more conditions met.")
    db.set_global_near_miss_threshold(value)
    return (f"✅ Global alert threshold set to **{value}/12** — applies to any "
            f"ticker without its own override.")


def _show_config_text() -> str:
    """Show the effective near-miss alert threshold for each watchlist ticker."""
    from data import database as db
    import yaml as _yaml

    default = 9
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                               "config.yaml")) as f:
            default = _yaml.safe_load(f)["strategy"].get(
                "near_miss_discord_threshold", 9)
    except Exception:
        pass

    glob = db.get_strategy_param("near_miss_threshold")
    glob_val = int(glob) if glob is not None else default
    lines = ["⚙️ ALERT CONFIG", "━━━━━━━━━━━━━━━━━━━━",
             f"Global threshold: {glob_val}/12", ""]
    for t in db.get_watchlist():
        per = db.get_strategy_param(f"near_miss_threshold_{t}")
        if per is not None:
            lines.append(f"• {t}: {int(per)}/12 (override)")
        else:
            lines.append(f"• {t}: {glob_val}/12 (global)")
    return "\n".join(lines)


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

    # The /analysis slash command needs NO privileged intents, so the bot
    # connects reliably by default. The plain-text "show analysis" trigger
    # requires the Message Content privileged intent, which must ALSO be
    # enabled in the Developer Portal — otherwise Discord refuses the gateway
    # connection. It's therefore opt-in via DISCORD_ENABLE_TEXT_COMMAND=true.
    text_command_enabled = os.getenv(
        "DISCORD_ENABLE_TEXT_COMMAND", "false").strip().lower() in ("1", "true", "yes")

    intents = discord.Intents.default()
    if text_command_enabled:
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

    def _wrong_channel(interaction) -> bool:
        return _channel is not None and interaction.channel_id != _channel.id

    @bot.tree.command(name="analysis",
                      description="Show fresh SMC analysis (optionally for one ticker)")
    @app_commands.describe(ticker="Optional ticker to analyse (e.g. META) — "
                                  "need not be on the watchlist")
    async def analysis_cmd(interaction, ticker: Optional[str] = None):
        if _wrong_channel(interaction):
            await interaction.response.send_message(
                f"Please use this command in #{_CHANNEL_NAME}.", ephemeral=True)
            return
        await interaction.response.defer()
        tickers = [ticker.strip().upper()] if ticker else None
        text = await asyncio.to_thread(_build_analysis_text, tickers)
        await interaction.followup.send(text[:_MAX_LEN])

    @bot.tree.command(name="add", description="Add a ticker to the watchlist")
    @app_commands.describe(ticker="Ticker symbol to add (e.g. META)")
    async def add_cmd(interaction, ticker: str):
        if _wrong_channel(interaction):
            await interaction.response.send_message(
                f"Please use this command in #{_CHANNEL_NAME}.", ephemeral=True)
            return
        await interaction.response.defer()
        text = await asyncio.to_thread(_add_ticker_text, ticker)
        await interaction.followup.send(text[:_MAX_LEN])

    @bot.tree.command(name="remove", description="Remove a ticker from the watchlist")
    @app_commands.describe(ticker="Ticker symbol to remove (e.g. META)")
    async def remove_cmd(interaction, ticker: str):
        if _wrong_channel(interaction):
            await interaction.response.send_message(
                f"Please use this command in #{_CHANNEL_NAME}.", ephemeral=True)
            return
        await interaction.response.defer()
        text = await asyncio.to_thread(_remove_ticker_text, ticker)
        await interaction.followup.send(text[:_MAX_LEN])

    @bot.tree.command(
        name="config",
        description="Set near-miss alert threshold (global, or per-ticker)")
    @app_commands.describe(
        value="Minimum conditions met (1-12) to trigger a near-miss alert",
        ticker="Optional ticker for a per-ticker override; omit to set global")
    async def config_cmd(interaction, value: int, ticker: Optional[str] = None):
        if _wrong_channel(interaction):
            await interaction.response.send_message(
                f"Please use this command in #{_CHANNEL_NAME}.", ephemeral=True)
            return
        await interaction.response.defer()
        text = await asyncio.to_thread(_config_text, ticker, value)
        await interaction.followup.send(text[:_MAX_LEN])

    @bot.tree.command(name="show",
                      description="Show the alert config for each watchlist ticker")
    async def show_cmd(interaction):
        if _wrong_channel(interaction):
            await interaction.response.send_message(
                f"Please use this command in #{_CHANNEL_NAME}.", ephemeral=True)
            return
        await interaction.response.defer()
        text = await asyncio.to_thread(_show_config_text)
        await interaction.followup.send(text[:_MAX_LEN])

    # Only register the plain-text trigger when the privileged intent is on;
    # without it message.content is always empty, so the handler is useless.
    if text_command_enabled:
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
