# SnipeBot — AI Options Trading Bot

A self-learning AI options trading bot that paper trades GOOGL, MSFT, TSLA, AAPL, and SPY. Runs 24/7 on a Mac Mini, learns from every trade, and notifies you via Discord.

**Paper trading only by default.** Switching to live requires a manual `.env` change — the bot will never do it automatically.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Get Your Alpaca API Keys](#2-get-your-alpaca-api-keys)
3. [Get Your Discord Webhook URL](#3-get-your-discord-webhook-url)
4. [Clone and Install](#4-clone-and-install)
5. [Configure Environment Variables](#5-configure-environment-variables)
6. [Review config.yaml](#6-review-configyaml)
7. [Run Manually (Test)](#7-run-manually-test)
8. [Deploy with macOS launchd (24/7)](#8-deploy-with-macos-launchd-247)
9. [File Structure](#9-file-structure)
10. [How the Bot Works](#10-how-the-bot-works)
11. [Self-Learning Engine](#11-self-learning-engine)
12. [Monitoring and Logs](#12-monitoring-and-logs)
13. [Going Live (When Ready)](#13-going-live-when-ready)
14. [Stopping and Halting](#14-stopping-and-halting)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| macOS | 12+ | Apple Silicon (M1/M2/M3) or Intel |
| Python | 3.11+ | Install via [python.org](https://www.python.org/downloads/) or `brew install python@3.11` |
| Homebrew | Any | Optional but recommended — [brew.sh](https://brew.sh) |
| Alpaca account | — | Free paper trading account |
| Discord server | — | Any server where you have permission to add webhooks |

Check your Python version:
```bash
python3 --version
```

---

## 2. Get Your Alpaca API Keys

Alpaca provides free paper trading accounts with full options support.

### Step 1 — Create an Alpaca Account

1. Go to [alpaca.markets](https://alpaca.markets) and click **Get Started**
2. Sign up with your email address
3. Verify your email

### Step 2 — Generate Paper Trading API Keys

1. Log in to your Alpaca dashboard
2. In the left sidebar, click **Paper Trading** (make sure you're NOT on Live Trading)
3. Click the **API Keys** tab (or navigate to [app.alpaca.markets/paper-trading/overview](https://app.alpaca.markets/paper-trading/overview))
4. Click **Generate New Key**
5. Copy both values immediately — the secret key is only shown once:
   - **API Key ID** → this is your `ALPACA_API_KEY`
   - **Secret Key** → this is your `ALPACA_SECRET_KEY`
6. Store them somewhere safe temporarily (you'll paste them into `.env` in Step 5)

> **Paper trading base URL:** `https://paper-api.alpaca.markets`  
> **Live trading base URL:** `https://api.alpaca.markets` (do NOT use this until you're ready)

### Step 3 — Enable Options Trading (Paper)

1. In the Alpaca dashboard, go to **Account → Account Settings**
2. Under **Agreements**, look for **Options Trading Agreement** and accept it
3. Paper trading options should now be available

---

## 3. Get Your Discord Webhook URL

Discord webhooks let the bot post messages to a channel without a bot token.

### Step 1 — Open Your Discord Server

1. Open Discord (desktop app or browser)
2. Navigate to the server and channel where you want bot notifications
   - Recommended: create a dedicated channel, e.g. `#snipebot-alerts`

### Step 2 — Create the Webhook

1. Right-click the channel name → **Edit Channel**
2. Click **Integrations** in the left menu
3. Click **Webhooks** → **New Webhook**
4. Name it `SnipeBot` (optional — any name works)
5. Click **Copy Webhook URL**
6. The URL looks like:
   ```
   https://discord.com/api/webhooks/1234567890123456789/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
7. Save this URL — this is your `DISCORD_WEBHOOK_URL`

---

## 4. Clone and Install

### Step 1 — Clone the Repository

```bash
git clone https://github.com/sirshishir/teen-patti-playroom.git
cd teen-patti-playroom/snipebot
```

### Step 2 — Create a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

You should see `(venv)` in your terminal prompt.

### Step 3 — Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This installs all required packages including `alpaca-py`, `scikit-learn`, `apscheduler`, `discord.py`, `yfinance`, and others. It may take 2–3 minutes.

---

## 5. Configure Environment Variables

### Step 1 — Copy the Template

```bash
cp .env.template .env
```

### Step 2 — Edit the `.env` File

Open `.env` in any text editor:

```bash
nano .env
```

Fill in your values:

```env
ALPACA_API_KEY=your_alpaca_api_key_here
ALPACA_SECRET_KEY=your_alpaca_secret_key_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_here
TRADING_MODE=paper
```

**Replace each placeholder:**

| Variable | What to paste |
|----------|--------------|
| `ALPACA_API_KEY` | The API Key ID from Alpaca (Step 2 above) |
| `ALPACA_SECRET_KEY` | The Secret Key from Alpaca (Step 2 above) |
| `ALPACA_BASE_URL` | Leave as `https://paper-api.alpaca.markets` for paper trading |
| `DISCORD_WEBHOOK_URL` | The full webhook URL from Discord (Step 3 above) |
| `TRADING_MODE` | Leave as `paper` |

Save and exit: `Ctrl+O`, `Enter`, `Ctrl+X` (for nano)

### Step 3 — Protect the File

```bash
chmod 600 .env
```

This prevents other users on the machine from reading your keys.

> **Never commit `.env` to git.** It is already in `.gitignore` by convention, but double-check with `git status` before any commit.

---

## 6. Review config.yaml

The `config.yaml` file controls all tunable strategy parameters. The defaults are set per the original spec and do not need to be changed before first run.

```yaml
trading:
  capital: 2000              # Starting capital in USD
  max_position_size: 200     # Max $ per options position
  max_open_positions: 3      # Max simultaneous open trades
  max_daily_loss: 300        # Bot halts trading if daily loss hits this

strategy:
  rsi_oversold: 35           # RSI threshold for CALL entries
  rsi_overbought: 65         # RSI threshold for PUT entries
  volume_ratio_min: 1.5      # Volume must be 1.5x the 20-day average
  vix_max: 30                # Skip trades when VIX >= 30
  min_dte: 14                # Minimum days to expiration
  max_dte: 30                # Maximum days to expiration
  ai_confidence_min: 0.72    # Minimum AI confidence score to fire
  take_profit_pct: 0.40      # Exit at +40% premium gain
  stop_loss_pct: 0.25        # Exit at -25% premium loss

ml:
  cold_start_trades: 50      # Use rule-based scoring until 50 trades logged
```

The self-learning engine will automatically adjust `rsi_oversold`, `rsi_overbought`, `stop_loss_pct`, `vix_max`, and per-ticker position sizes. You don't need to manually tune these.

---

## 7. Run Manually (Test)

Before setting up auto-start, verify everything works:

```bash
# Make sure venv is active
source venv/bin/activate

# From the snipebot/ directory
python main.py
```

**Expected output on first run:**
```
HH:MM:SS [INFO] __main__: SnipeBot starting up...
HH:MM:SS [INFO] data.database: Database initialised at /path/to/snipebot.db
HH:MM:SS [INFO] __main__: APScheduler starting with 5 jobs
HH:MM:SS [INFO] __main__:   Job: sr_cache | Cache S/R Zones
HH:MM:SS [INFO] __main__:   Job: scanner | Market Scanner
HH:MM:SS [INFO] __main__:   Job: position_monitor | Position Monitor
HH:MM:SS [INFO] __main__:   Job: daily_report | Daily Report
HH:MM:SS [INFO] __main__:   Job: weekly_learning | Weekly Learning
```

You should also see a `🟢 SnipeBot is ONLINE` message appear in your Discord channel.

Press `Ctrl+C` to stop after confirming it works.

---

## 8. Deploy with macOS launchd (24/7)

`launchd` is macOS's built-in service manager. It will start SnipeBot on boot and restart it if it crashes.

### Step 1 — Find Your Absolute Path

```bash
pwd
```

This prints something like `/Users/yourname/teen-patti-playroom/snipebot`. Copy it.

### Step 2 — Edit the plist File

```bash
nano launchd/com.snipebot.plist
```

Replace **all four** occurrences of `/path/to/snipebot` with your actual path:

```xml
<string>/Users/yourname/teen-patti-playroom/snipebot/venv/bin/python</string>
<string>/Users/yourname/teen-patti-playroom/snipebot/main.py</string>
...
<string>/Users/yourname/teen-patti-playroom/snipebot/logs/stdout.log</string>
<string>/Users/yourname/teen-patti-playroom/snipebot/logs/stderr.log</string>
...
<string>/Users/yourname/teen-patti-playroom/snipebot</string>
...
<string>/usr/local/bin:/usr/bin:/bin:/Users/yourname/teen-patti-playroom/snipebot/venv/bin</string>
```

Save and exit.

### Step 3 — Copy to LaunchAgents

```bash
cp launchd/com.snipebot.plist ~/Library/LaunchAgents/com.snipebot.plist
```

### Step 4 — Load the Service

```bash
launchctl load ~/Library/LaunchAgents/com.snipebot.plist
```

### Step 5 — Verify It's Running

```bash
launchctl list | grep snipebot
```

You should see a line like:
```
12345   0   com.snipebot
```

The middle number `0` means it's running without errors. A non-zero number is an exit code (check `logs/stderr.log` if so).

### Step 6 — Check Logs

```bash
tail -f logs/snipebot.log
```

### Managing the Service

```bash
# Stop SnipeBot
launchctl unload ~/Library/LaunchAgents/com.snipebot.plist

# Start SnipeBot
launchctl load ~/Library/LaunchAgents/com.snipebot.plist

# Restart (stop then start)
launchctl unload ~/Library/LaunchAgents/com.snipebot.plist
launchctl load ~/Library/LaunchAgents/com.snipebot.plist
```

---

## 9. File Structure

```
snipebot/
├── main.py                        # Entry point — starts scheduler and all jobs
├── config.yaml                    # All tunable strategy parameters
├── .env                           # API keys (never commit this)
├── .env.template                  # Safe template to commit
├── requirements.txt               # Python dependencies
├── snipebot.db                    # SQLite database (auto-created on first run)
├── HALT.txt                       # Create this file to pause all trading immediately
│
├── core/
│   ├── scanner.py                 # 5-min market scanner
│   ├── strategy.py                # Entry/exit decision logic
│   ├── indicators.py              # RSI, MACD, volume, S/R zone detection
│   ├── risk_manager.py            # Position sizing, daily loss limit
│   └── order_executor.py          # Alpaca API calls
│
├── ml/
│   ├── confidence_model.py        # Random Forest classifier
│   ├── feature_engineer.py        # Feature vector builder
│   └── learner.py                 # Weekly self-learning loop
│
├── data/
│   ├── database.py                # SQLite interface
│   └── market_data.py             # Fetch OHLCV, options chain, VIX
│
├── notifications/
│   └── discord_bot.py             # Discord message templates and sender
│
├── reports/
│   └── daily_report.py            # End-of-day report generator
│
├── models/
│   └── confidence_model.pkl       # Trained ML model (auto-updated weekly)
│
├── logs/
│   ├── snipebot.log               # Rotating log (7-day retention)
│   ├── learning_log.txt           # Human-readable record of every learning change
│   ├── stdout.log                 # launchd stdout
│   └── stderr.log                 # launchd stderr
│
└── launchd/
    └── com.snipebot.plist         # macOS launchd config
```

---

## 10. How the Bot Works

### Scheduler (All Times US/Eastern)

| Job | Schedule |
|-----|----------|
| Cache S/R zones | Daily 9:00 AM, Mon–Fri |
| Market scanner | Every 5 min, Mon–Fri, 9:35 AM – 3:45 PM |
| Position monitor | Every 1 min, Mon–Fri, 9:35 AM – 3:55 PM |
| Daily report | Daily 4:15 PM, Mon–Fri |
| Weekly learning | Every Sunday 8:00 PM |

### Entry Logic (ALL must pass simultaneously)

1. Price is within an auto-detected Support/Resistance zone (±0.3% tolerance)
2. RSI(14) < 35 for calls, or RSI(14) > 65 for puts
3. MACD histogram has just crossed in the trade direction (bullish for calls, bearish for puts)
4. Volume spike > 1.5× the 20-day average
5. AI confidence score ≥ 0.72
6. No earnings announcement within the next 5 calendar days
7. VIX < 30
8. Not within the last 15 minutes of the trading day

### Exit Logic

| Trigger | Threshold |
|---------|-----------|
| Take Profit | +40% on option premium |
| Stop Loss | −25% on option premium |
| Time Stop | Exit 1 day before expiration |
| Trailing Stop | Once +20% reached, trail −10% from peak |

### Options Selection

- Buys calls or puts only (no naked selling)
- Expiry: 14–30 DTE
- Strike: ATM or 1 strike OTM
- Max per position: $200
- Max simultaneous open positions: 3
- Max 1 trade per ticker per day

---

## 11. Self-Learning Engine

Every Sunday at 8:00 PM ET, the bot automatically:

1. Pulls all trades from the last 30 days
2. Computes win rate, avg win, avg loss, and expectancy per ticker
3. Applies adjustment rules:

| Condition | Action |
|-----------|--------|
| Win rate < 45% | Tighten RSI threshold by 2 points |
| Avg loss > avg win × 1.5 | Reduce stop loss from −25% to −20% |
| Ticker win rate < 40% over 20+ trades | Reduce that ticker's position size by 25% |
| VIX trades consistently losing | Raise VIX threshold by 2 |
| Win rate > 65% for 4+ weeks | Loosen RSI threshold by 1 point |

4. Retrains the Random Forest model on all historical trades
5. Logs every change with timestamp and reason to `logs/learning_log.txt`
6. Sends a Discord Weekly Learning Update

**Cold start:** For the first 50 trades, a rule-based weighted score is used instead of the ML model. After 50 trades the model trains automatically and takes over.

---

## 12. Monitoring and Logs

### Real-time log

```bash
tail -f logs/snipebot.log
```

### Learning log (what the bot changed and why)

```bash
cat logs/learning_log.txt
```

### SQLite database (direct inspection)

```bash
sqlite3 snipebot.db

# Recent trades
SELECT ticker, direction, entry_price, exit_price, pnl, outcome FROM trades ORDER BY id DESC LIMIT 20;

# Win rate
SELECT outcome, COUNT(*) FROM trades WHERE outcome IS NOT NULL GROUP BY outcome;

# Current strategy params (learning overrides)
SELECT * FROM strategy_params;

# Daily performance history
SELECT * FROM daily_performance ORDER BY date DESC LIMIT 10;

.quit
```

### Discord Notifications

You will receive messages for:
- Every trade entry (🎯 SNIPE FIRED)
- Every trade exit (✅ WIN / ❌ LOSS)
- Daily report at 4:15 PM ET (📊)
- Weekly learning update every Sunday (🧠)
- Daily loss limit alert if triggered (⚠️)
- Data error alerts if a ticker fails 3 consecutive fetches (🔴)
- 100-trade milestone notification (📊)

---

## 13. Going Live (When Ready)

After reviewing paper trading results for 3–4 months:

1. Log in to Alpaca and generate **Live Trading** API keys (separate from paper keys)
2. Complete Alpaca's identity verification if not already done
3. Fund your account with $2,000 via ACH transfer or wire
4. Update `.env`:

```env
ALPACA_API_KEY=your_live_api_key
ALPACA_SECRET_KEY=your_live_secret_key
ALPACA_BASE_URL=https://api.alpaca.markets
TRADING_MODE=live
```

5. Restart the bot:

```bash
launchctl unload ~/Library/LaunchAgents/com.snipebot.plist
launchctl load ~/Library/LaunchAgents/com.snipebot.plist
```

> **The bot will never switch to live on its own.** This is a deliberate safety gate. You must change `.env` manually.

---

## 14. Stopping and Halting

### Emergency pause (without stopping the bot)

Create a `HALT.txt` file in the `snipebot/` directory:

```bash
touch HALT.txt
```

The scanner will immediately skip all signal evaluation and order placement on its next cycle. Remove the file to resume:

```bash
rm HALT.txt
```

### Stop the bot entirely

```bash
launchctl unload ~/Library/LaunchAgents/com.snipebot.plist
```

### Stop and prevent auto-restart on boot

```bash
launchctl unload ~/Library/LaunchAgents/com.snipebot.plist
rm ~/Library/LaunchAgents/com.snipebot.plist
```

---

## 15. Troubleshooting

### Bot isn't starting

```bash
# Check launchd status
launchctl list | grep snipebot

# Check for errors
cat logs/stderr.log
```

### Discord messages not arriving

1. Verify `DISCORD_WEBHOOK_URL` in `.env` is correct and complete
2. Test the webhook manually:
   ```bash
   curl -X POST -H "Content-Type: application/json" \
     -d '{"content": "test message"}' \
     "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"
   ```
3. Check the webhook still exists in Discord (Server Settings → Integrations → Webhooks)

### Alpaca API errors

1. Confirm `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` are correct in `.env`
2. Make sure you're using **paper** keys with the **paper** base URL (they are different from live keys)
3. Check [status.alpaca.markets](https://status.alpaca.markets) for outages
4. Paper trading keys start fresh — you may need to regenerate them if they've expired

### `ModuleNotFoundError`

The virtual environment is likely not active or the plist path is wrong:

```bash
# Verify venv has packages
/path/to/snipebot/venv/bin/python -c "import alpaca; print('ok')"

# Re-install if needed
source venv/bin/activate
pip install -r requirements.txt
```

### No trades firing

This is expected behaviour — SnipeBot is intentionally patient. Check `logs/snipebot.log` for lines like:
- `Signal candidate:` — the bot is evaluating signals
- `in_sr_zone: False` — price not near a zone (most common reason)
- `MACD crossover not aligned` — waiting for crossover confirmation

You can lower `ai_confidence_min` in `config.yaml` temporarily to see more activity during testing.

### `HALT.txt` left behind accidentally

```bash
ls HALT.txt   # check if it exists
rm HALT.txt   # remove it
```

---

## Security Notes

- `.env` contains your API keys — never share it, never commit it to git
- Alpaca paper keys can only place paper trades — they cannot touch real money even if leaked
- Live keys should be treated like a password; rotate them if compromised via the Alpaca dashboard
- The bot does not store keys anywhere other than `.env` and in-memory environment variables
