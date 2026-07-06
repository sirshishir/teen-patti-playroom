# SnipeBot — Self-Learning AI Options Trading Bot

SnipeBot is an automated options trading bot that uses **Smart Money Concepts (SMC/ICT)** technical analysis combined with a **self-learning Random Forest** AI model. It scans 5 tickers every 30 minutes across a 4-timeframe stack (Weekly → Daily → 4H → 1H), fires precise entry signals, manages positions with adaptive exits, and sends rich Discord notifications.

---

## Features

### Trading Strategy — Smart Money Concepts (SMC/ICT)
- **Multi-timeframe analysis**: Weekly macro bias → Daily structure → 4H order blocks → 1H entry trigger
- **Market structure**: Detects BOS (Break of Structure) and CHOCH (Change of Character) via swing-point analysis
- **Liquidity zones**: Identifies equal highs/lows and sweep events that signal institutional positioning
- **Order blocks**: Detects unmitigated bullish/bearish order blocks on Daily and 4H timeframes
- **Fibonacci retracement**: Requires price to be in the 0.618–0.786 golden zone before entry
- **12-condition entry gate**: All conditions must be satisfied simultaneously — weekly bias, daily structure, liquidity sweep, Fibonacci zone, order block confluence, RVOL ≥ 1.5×, ATR expansion, session timing, AI confidence, earnings buffer, VIX filter, end-of-day gate

### Options Selection
- Targets **14–30 DTE** options (appropriate horizon for SMC swing setups)
- Selects nearest at-the-money contract
- Take profit: **+40%** | Stop loss: **-25%** | Trailing stop: activates at +20%, trails 10%

### AI Confidence Model
- **Cold start (< 50 trades)**: Rule-based weighted score (structure 25%, Fibonacci 25%, OB 20%, RVOL 15%, ATR 10%, 4H confluence 5%)
- **Post cold-start**: Random Forest classifier trained on all historical trades
- **Auto-retrains** every Sunday via the weekly learning loop

### Self-Learning (Weekly, Sunday 8 PM ET)
- Win rate < 45% → tighten Fibonacci entry zone
- Average loss > 1.5× average win → tighten stop loss
- Per-ticker win rate < 40% over 20+ trades → reduce position size 25%
- High-VIX win rate < 35% → raise VIX max threshold
- Sustained win rate > 65% → loosen Fibonacci zone

### Risk Management
- Max $200 per position
- Max $300 daily loss (trading halts automatically)
- Per-ticker position size adjustable by the learner
- Earnings buffer: skips entry within 5 days of earnings

### Broker Support
- **Alpaca** (default): paper and live, full options chain
- **Webull** (optional): set `BROKER=webull` in `.env` — routes all orders, data, and options chain through the Webull Developer API
- **yfinance**: universal fallback for market data when the primary broker is unavailable

### Notifications — Discord
Delivered either via a **gateway bot** (recommended — enables slash commands) or
a **webhook** (fallback). Message types:
1. Trade Entry — signal details, TP/SL levels, AI confidence (`🧪 SEED` prefix for virtual seed trades)
2. Trade Exit — PnL, exit reason, hold time
3. Daily Report (4:15 PM ET) — trades, PnL, portfolio value, 30-day win rate
4. Weekly Learning Update (Sunday 8 PM ET) — parameter changes, model accuracy, near-miss stats
5. Daily Loss Limit Hit — immediate alert when the daily loss limit is reached
6. System Alerts — bot online, data errors, 100-trade milestone
7. Near-Miss — per-condition ✅/❌ breakdown (with the *reason* for each) when a
   setup reaches the alert threshold but doesn't fire

### Interactive Discord Commands (gateway bot)
Run these in the bot's channel (`#price-alert` by default):
| Command | What it does |
|---------|--------------|
| `/analysis` | Fresh SMC analysis of the whole watchlist (recomputed live, not cached) |
| `/analysis ticker:META` | Analyse any ticker — even one not on the watchlist |
| `/add ticker:META` | Add a ticker to the watchlist (validated + persisted) |
| `/remove ticker:META` | Remove a ticker from the watchlist |
| `/config value:9` | Set the global near-miss alert threshold (conditions met, 1–12) |
| `/config value:10 ticker:META` | Set a per-ticker alert-threshold override |
| `/show` | Show each watchlist ticker's effective alert threshold |

### Companion: Day-Trade Alerts Bot (`daytrader/`)
A separate, self-contained **alerts-only** bot (never places orders) that posts
intraday level/zone alerts to a **`#day-trade`** channel. It shares the repo,
`.env`, and venv but has its own database and runs as its own process. See the
[Day-Trade Alerts Bot](#day-trade-alerts-bot-daytrader) section below.

### Data accuracy
Analysis uses Alpaca's **SIP** consolidated feed (full-volume, 15-min-delayed on
the free tier via `ALPACA_FEED`), split/dividend-**adjusted** bars, session-aligned
09:30 RTH candles, and evaluates on **completed bars only**. The VIX gate fails
**closed** (a data outage halts trading rather than enabling it).

---

## Prerequisites

- Python 3.11+
- A **free** [Alpaca Markets](https://alpaca.markets) account (paper trading) or live account
- A [Discord](https://discord.com) server with a webhook URL
- *(Optional)* A [Webull Developer](https://developer.webull.com) account for Webull broker
- *(For cloud deployment)* [Fly.io](https://fly.io) account or Oracle Cloud Always Free account

---

## Step 1 — Alpaca API Keys

1. Go to [alpaca.markets](https://alpaca.markets) and sign up for a free account.
2. In the dashboard, select **Paper Trading** (top-left toggle).
3. Click **Generate New Keys** under **API Keys**.
4. Copy your **API Key ID** and **Secret Key** — the secret is shown only once.
5. Your paper trading base URL is: `https://paper-api.alpaca.markets`

> To go live later, switch to the Live account tab, generate live keys, and change `ALPACA_BASE_URL` to `https://api.alpaca.markets`. **The bot will never do this automatically.**

---

## Step 2 — Webull Developer API Keys (optional)

Only required if you set `BROKER=webull`.

1. Go to [developer.webull.com](https://developer.webull.com) and register for a developer account.
2. Create a new application to get your **App Key** and **App Secret**.
3. Find your **Account ID** in the Webull desktop app under **Account → Account Summary**.
4. The bot uses OAuth2 `client_credentials` grant — no user login required.

> **Note**: Webull Developer API endpoints should be verified against your developer account documentation, as paths may differ between regions and API versions. The bot uses standard REST patterns with `# verify path` comments where confirmation is needed.

---

## Step 3 — Discord

SnipeBot supports two delivery methods (auto-detected). **Option A is recommended**
because it enables the interactive slash commands (`/analysis`, `/add`, …).

**Option A — Gateway bot (recommended):**
1. [discord.com/developers/applications](https://discord.com/developers/applications) → **New Application** → **Bot** → **Reset Token** → copy the **bot token** → `DISCORD_BOT_TOKEN`.
2. Invite the bot to your server with **Send Messages** + **Use Slash Commands** in the target channel.
3. Set `DISCORD_CHANNEL_NAME=price-alert` (the channel it posts in, without `#`).
4. *(Optional)* To use the plain-text `show analysis` trigger, enable **MESSAGE CONTENT INTENT** in the Bot page and set `DISCORD_ENABLE_TEXT_COMMAND=true`. The `/analysis` slash command works without this.

**Option B — Webhook (fallback, no commands):**
1. Server settings → **Integrations** → **Webhooks** → **New Webhook** → choose a channel → **Copy Webhook URL** → `DISCORD_WEBHOOK_URL`.

> If the gateway bot is configured it takes precedence; the webhook is used only when the bot isn't connected.

---

## Step 4 — Local Setup

```bash
# Clone the repo and enter the snipebot directory
git clone https://github.com/sirshishir/teen-patti-playroom.git
cd teen-patti-playroom/snipebot

# Create a virtual environment
python3.11 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy the secrets template and fill it in
cp .env.template .env
chmod 600 .env                   # restrict read access (Linux/macOS)
nano .env                        # or use any text editor
```

**`.env` file contents:**

```env
# Broker: "alpaca" (default) or "webull"
BROKER=alpaca

# Alpaca
ALPACA_API_KEY=your_alpaca_api_key
ALPACA_SECRET_KEY=your_alpaca_secret_key
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Webull (only needed if BROKER=webull)
WEBULL_APP_KEY=your_webull_app_key
WEBULL_APP_SECRET=your_webull_app_secret
WEBULL_ACCOUNT_ID=your_webull_account_id

# Discord
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook

# Paper mode — change to "live" ONLY after reviewing paper results manually
TRADING_MODE=paper
```

> **Security**: Never commit `.env` to git. It is listed in `.gitignore` and `.dockerignore`.

---

## Step 5 — Configuration

Edit `config.yaml` to adjust strategy parameters. Key settings:

```yaml
trading:
  capital: 2000.0          # Starting capital in USD
  max_position_size: 200   # Max $ per trade
  max_daily_loss: 300      # Daily loss halt threshold

strategy:
  fib_zone_min: 0.618      # Fibonacci entry zone lower bound
  fib_zone_max: 0.786      # Fibonacci entry zone upper bound
  rvol_min: 1.5            # Minimum relative volume multiplier
  vix_max: 30              # Maximum VIX level to trade
  min_dte: 14              # Minimum days-to-expiry
  max_dte: 30              # Maximum days-to-expiry
  ai_confidence_min: 0.72  # Minimum AI confidence to fire
```

---

## Step 6 — Running Locally

```bash
cd teen-patti-playroom/snipebot
source venv/bin/activate
python main.py
```

The scheduler runs:

| Job | Schedule | Description |
|-----|----------|-------------|
| Cache warm-up | 9:00 AM ET | Builds Weekly/Daily/4H SMC analysis per ticker |
| Market scanner | Every 30 min (9:30 AM–3:30 PM ET) | Checks all 12 SMC conditions, fires trades |
| Position monitor | Every 5 min (9:35 AM–3:55 PM ET) | Checks TP/SL/trailing stop |
| Daily report | 4:15 PM ET | Sends Discord daily summary |
| Weekly learner | Sunday 8:00 PM ET | Retrains model, adjusts parameters |

Logs are written to `logs/snipebot.log`. The SQLite database is at `snipebot.db`.

---

## Step 7 — Docker

### Build the image

```bash
cd teen-patti-playroom/snipebot
docker build -t snipebot .
```

### Run locally with Docker

```bash
docker run -d \
  --name snipebot \
  --env-file .env \
  -v snipebot_data:/data \
  snipebot
```

Logs:
```bash
docker logs -f snipebot
```

---

## Step 8 — Deploy to Fly.io (~$5/month)

Fly.io runs SnipeBot as a persistent background worker with a mounted volume for the SQLite database and logs.

> The committed `fly.toml` declares **two processes** (`snipebot` + `daytrader`),
> so a deploy starts **two machines**. The steps below cover the `snipebot`
> process; for the second `daytrader` machine (its own `daytrader_data` volume +
> the `#day-trade` webhook) see [Day-Trade Alerts Bot](#day-trade-alerts-bot-daytrader).
> If you only want SnipeBot for now, you can remove the `daytrader` entry from
> `[processes]` and the `daytrader_data` mount.

### 8a — Install Fly CLI

```bash
# macOS
brew install flyctl

# Linux
curl -L https://fly.io/install.sh | sh

# Authenticate
fly auth login
```

### 8b — Create the app

```bash
cd teen-patti-playroom/snipebot

# Create the app WITHOUT letting Fly scaffold a web service.
# --copy-config reuses the committed fly.toml (a background worker with no
# HTTP port); --name sets a globally unique app name.
# Replace "my-snipebot" with any globally unique name.
fly launch --no-deploy --copy-config --name my-snipebot --region ord
```

> **Important:** always pass `--copy-config`. Without it, `fly launch` tries to auto-detect a web app and injects an `[http_service]` that points at a process named `app`, which fails validation for a background worker (`Service specifies 'app' as one of its processes, but no processes are defined with that name`). The committed `fly.toml` has no `[processes]` and no service — Fly runs the Dockerfile's `CMD` (`python main.py`) as the single default process.

After launch, make sure `app = "..."` in `fly.toml` matches the `--name` you chose.

### 8c — Create the persistent volume

```bash
# 1 GB is plenty for SQLite + logs
fly volumes create snipebot_data --region ord --size 1
```

### 8d — Set secrets

Secrets are injected as environment variables at runtime — they are **never** baked into the image.

```bash
# Required
fly secrets set ALPACA_API_KEY=your_key
fly secrets set ALPACA_SECRET_KEY=your_secret
fly secrets set ALPACA_BASE_URL=https://paper-api.alpaca.markets
fly secrets set DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook
fly secrets set TRADING_MODE=paper

# Optional — only if BROKER=webull
fly secrets set BROKER=webull
fly secrets set WEBULL_APP_KEY=your_webull_key
fly secrets set WEBULL_APP_SECRET=your_webull_secret
fly secrets set WEBULL_ACCOUNT_ID=your_account_id
```

### 8e — Deploy

```bash
fly deploy
```

### 8f — Monitor

```bash
fly logs                   # live log stream
fly status                 # VM health
fly ssh console            # SSH into the container
```

### 8g — Scale down to save cost

```bash
# Pause the machine when markets are closed (e.g. weekends)
fly scale count 0          # stop
fly scale count 1          # restart
```

---

## Step 9 — Deploy to Oracle Cloud Always Free (free forever)

Oracle Cloud provides a genuinely free Always Free tier with 2 AMD VMs (1 GB RAM each) that never expire — a good alternative to Fly.io.

### 9a — Create an Always Free VM

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com).
2. Create a **Compute Instance** → shape **VM.Standard.E2.1.Micro** (Always Free).
3. Choose **Ubuntu 22.04** as the OS.
4. Download the SSH key during setup.

### 9b — Connect and set up

```bash
ssh -i ~/your-key.pem ubuntu@<YOUR_VM_IP>

# Install Python 3.11 and git
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip git

# Clone the repo
git clone https://github.com/sirshishir/teen-patti-playroom.git
cd teen-patti-playroom/snipebot

# Set up virtualenv and install packages
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env (never commit this)
cp .env.template .env
chmod 600 .env
nano .env    # fill in all keys
```

### 9c — Run as a systemd service

```bash
sudo nano /etc/systemd/system/snipebot.service
```

Paste the following (update paths as needed):

```ini
[Unit]
Description=SnipeBot AI Options Trading Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/teen-patti-playroom/snipebot
EnvironmentFile=/home/ubuntu/teen-patti-playroom/snipebot/.env
ExecStart=/home/ubuntu/teen-patti-playroom/snipebot/venv/bin/python main.py
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable snipebot
sudo systemctl start snipebot
sudo systemctl status snipebot
journalctl -u snipebot -f     # live logs
```

---

## Step 10 — macOS (launchd)

A launchd plist is provided at `launchd/com.snipebot.plist`. Edit the file paths to match your system, then:

```bash
cp launchd/com.snipebot.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.snipebot.plist
launchctl start com.snipebot
```

---

## Secret Management with Doppler (optional)

[Doppler](https://doppler.com) provides free secret management — store all keys in Doppler and inject them at runtime instead of using `.env` files on the server.

```bash
# Install Doppler CLI
curl -Ls https://cli.doppler.com/install.sh | sh

# Link the project
doppler login
doppler setup

# Run with Doppler-injected secrets
doppler run -- python main.py

# For systemd, replace ExecStart with:
# ExecStart=/usr/bin/doppler run -- /path/to/venv/bin/python main.py
```

---

## Project Structure

```
snipebot/
├── main.py                  # SnipeBot entrypoint — APScheduler jobs + gateway bot
├── config.yaml              # Strategy, trading, and ML parameters
├── requirements.txt         # Python dependencies
├── .env.template            # Secrets template (copy to .env)
├── Dockerfile               # Multi-stage Docker build
├── fly.toml                 # Fly.io config (2 processes: snipebot + daytrader)
├── .dockerignore            # Excludes .env, venv, logs, DB
├── core/
│   ├── indicators.py        # SMC engine (swings, OBs w/ as_of, Fibonacci, RVOL, ATR)
│   ├── strategy.py          # 12-condition entry gate + per-condition reasons
│   ├── scanner.py           # 30-min scan, seed trades, on-demand /analysis
│   ├── risk_manager.py      # Position sizing, daily loss gate, trailing stop
│   └── order_executor.py    # Alpaca + Webull order routing
├── data/
│   ├── database.py          # SQLite CRUD (trades, watchlist, thresholds, candidates)
│   ├── market_data.py       # SIP OHLCV, options chain, VIX; multi-broker routing
│   ├── bars.py              # Session-aligned RTH resampler (one bar factory)
│   └── webull_client.py     # Webull OAuth2 REST client
├── ml/
│   ├── confidence_model.py  # RandomForest confidence scorer
│   ├── feature_engineer.py  # 9-feature SMC vector builder
│   └── learner.py           # Sunday self-learning loop
├── notifications/
│   ├── discord_bot.py       # Message templates + delivery (bot or webhook)
│   └── discord_client.py    # Persistent gateway bot + slash commands
├── reports/
│   ├── daily_report.py      # 4:15 PM ET daily report
│   └── analysis_snapshot.py # /analysis report formatter
├── daytrader/               # Companion day-trade ALERTS bot (never places orders)
│   ├── main.py              # Its own scheduler loop (python -m daytrader.main)
│   ├── config.yaml          # Day-trade tickers, levels, calibration config
│   ├── levels_engine.py     # Zones, reference levels, ATR/RVOL
│   ├── scorer.py            # Per-touch confidence model
│   ├── calibrate.py         # Nightly quantiles + triple-barrier labels
│   ├── backtest.py          # Walk-forward validation / calibration seeding
│   ├── alerts.py            # #day-trade webhook sender
│   ├── analyst.py           # Weekly Claude analyst (optional)
│   └── store.py             # daytrader.db persistence
├── tests/
│   └── test_fixes.py        # Data-accuracy regression tests
├── launchd/
│   └── com.snipebot.plist   # macOS launchd config
└── models/
    └── confidence_model.pkl # Persisted RandomForest (auto-generated)
```

---

## Day-Trade Alerts Bot (`daytrader/`)

A **separate, self-contained** bot that posts intraday level/zone alerts to a
`#day-trade` channel. It is **alerts-only and never places orders** (PDT rules
apply at small account sizes). It shares the repo, `.env`, and venv, but has
**zero code coupling** to SnipeBot's `core/`/`data/`, its own database
(`daytrader.db`), and runs as its **own process**.

### How it fits together
- **One Fly app, two processes → two machines** from a single image/deploy:
  `snipebot` (`python main.py`) and `daytrader` (`python -m daytrader.main`).
- Each machine mounts **its own** volume at `/data` (`snipebot_data` /
  `daytrader_data`) — Fly volumes can't be shared across machines.
- Discord: SnipeBot uses its gateway bot in `#price-alert`; daytrader uses a
  plain **webhook** in `#day-trade` (no separate Discord app needed).

### Setup (Fly dashboard — no CLI required)
1. **Discord webhook:** create channel `#day-trade` → Edit Channel → Integrations
   → Webhooks → New Webhook → copy URL → set secret `DISCORD_DAYTRADE_WEBHOOK_URL`.
2. **Volume:** Fly dashboard → Volumes → Create `daytrader_data` (region `ord`, 1 GB).
3. **Secrets** (Fly dashboard → Secrets): `DISCORD_DAYTRADE_WEBHOOK_URL`, and
   optionally `ANTHROPIC_API_KEY` (weekly analyst only — the bot runs without it).
4. **Deploy** `main` as usual. Fly starts both machines; confirm **two** machines
   in the dashboard's Machines view.

### Seeding calibration (run the backtest without a terminal)
Set the secret `DAYTRADER_BACKTEST_ON_START=1` (optionally
`DAYTRADER_BACKTEST_START` / `DAYTRADER_BACKTEST_END`), then deploy. On boot the
daytrader machine runs the walk-forward backtest once, **posts the per-level
report to `#day-trade`**, commits calibration to `daytrader.db`, and continues
into the live loop. **Review the report** — level types with n ≥ 20 and
win% > ~52% carry edge; near coin-flip means keep collecting. Then **delete the
`DAYTRADER_BACKTEST_ON_START` secret** so it doesn't re-run every deploy (the
nightly job keeps calibration fresh thereafter).

Locally you can instead run:
```bash
python -m daytrader.backtest --start 2025-01-02 --end 2026-06-30 --commit
python -m daytrader.main
```

### Weekly cadence
Sun 19:00 ET scorer retrain → 19:30 ET optional Claude analyst posts a Weekly
Analyst Review to `#day-trade`. It never auto-merges or auto-deploys; any config
proposal is posted for you to review. (PR mode needs the `gh` CLI on the host,
which a Fly container lacks — set `analyst.enable_pr: false` in
`daytrader/config.yaml`, which posts a diff to Discord instead.)

---

## Switching to Live Trading

> **Read this carefully before going live.**

1. Complete at least **100 paper trades** and review `logs/learning_log.txt`.
2. Verify the win rate and expectancy in Discord daily/weekly reports.
3. Open your `.env` file and make **two manual changes**:
   ```env
   ALPACA_BASE_URL=https://api.alpaca.markets
   TRADING_MODE=live
   ```
4. Restart the bot.

The bot will **never** switch to live mode automatically. A human must change `.env`.

---

## Watchlist

The watchlist is stored in the database (`watchlist` table), seeded on first run
with `GOOGL, MSFT, TSLA, AAPL, SPY`. It is the single source of truth — the
scanner, the 9 AM analysis cache, and the weekly learner all read it via
`db.get_watchlist()`.

To change it, use the Discord commands (no code edits, no redeploy):
- `/add ticker:META` — add a ticker
- `/remove ticker:META` — remove a ticker
- `/show` — list the watchlist and per-ticker alert thresholds

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `DISCORD_WEBHOOK_URL not set` | Check `.env` is in the same directory as `main.py` and `python-dotenv` is installed |
| Alpaca `401 Unauthorized` | Double-check `ALPACA_API_KEY` and `ALPACA_SECRET_KEY`; ensure paper vs live URL matches |
| `Empty response` for a ticker | Market may be closed or the ticker is invalid; check `ALPACA_BASE_URL` |
| Webull `401` on startup | Verify `WEBULL_APP_KEY` and `WEBULL_APP_SECRET`; token auto-refreshes every ~23 hours |
| Bot fires no trades | All 12 conditions must align — this is intentional. Check `logs/snipebot.log` for which condition is failing |
| Model not retraining | Requires `ml.cold_start_trades` (default 50) closed trades in the DB |

---

## License

This project is for educational and personal use. Options trading involves substantial risk of loss. This software does not constitute financial advice. Never risk money you cannot afford to lose.
