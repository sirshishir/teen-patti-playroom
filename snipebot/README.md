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

### Notifications — Discord (6 message types)
1. Trade Entry — full signal details, TP/SL levels, AI confidence
2. Trade Exit — PnL, exit reason, hold time
3. Daily Report (4:15 PM ET) — trades, PnL, portfolio value, 30-day win rate
4. Weekly Learning Update (Sunday 8 PM ET) — parameter changes, model accuracy
5. Daily Loss Limit Hit — immediate alert when daily loss limit is reached
6. System Alerts — bot online, data errors, 100-trade milestone

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

## Step 3 — Discord Webhook

1. Open your Discord server settings → **Integrations** → **Webhooks**.
2. Click **New Webhook**, name it (e.g., `SnipeBot`), choose a channel.
3. Click **Copy Webhook URL**.

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

# Create the app (no deploy yet)
# Replace "my-snipebot" with any globally unique name
fly launch --name my-snipebot --no-deploy --region ord
```

This creates a `fly.toml` linked to your account. Update `app = "snipebot"` in `fly.toml` to match your chosen name.

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
├── main.py                  # APScheduler — all 5 jobs wired here
├── config.yaml              # Strategy and trading parameters
├── requirements.txt         # Python dependencies
├── .env.template            # Secrets template (copy to .env)
├── Dockerfile               # Multi-stage Docker build
├── fly.toml                 # Fly.io deployment config
├── .dockerignore            # Excludes .env, venv, logs, DB
├── core/
│   ├── indicators.py        # Full SMC engine (swing points, OBs, Fibonacci, RVOL, ATR)
│   ├── strategy.py          # 12-condition entry gate + signal builder
│   ├── scanner.py           # 30-minute scan loop
│   ├── risk_manager.py      # Position sizing, daily loss gate, trailing stop
│   └── order_executor.py    # Alpaca + Webull order routing
├── data/
│   ├── database.py          # SQLite CRUD (trades, strategy params, daily performance)
│   ├── market_data.py       # OHLCV, options chain, VIX, earnings; multi-broker routing
│   └── webull_client.py     # Webull OAuth2 REST client
├── ml/
│   ├── confidence_model.py  # RandomForest confidence scorer
│   ├── feature_engineer.py  # 9-feature SMC vector builder
│   └── learner.py           # Sunday self-learning loop
├── notifications/
│   └── discord_bot.py       # 6 Discord message templates
├── reports/
│   └── daily_report.py      # 4:15 PM ET daily report
├── launchd/
│   └── com.snipebot.plist   # macOS launchd config
└── models/
    └── confidence_model.pkl # Persisted RandomForest (auto-generated)
```

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

The default watchlist is: `GOOGL, MSFT, TSLA, AAPL, SPY`

To change it, edit the `watchlist` list in `data/market_data.py` (inside `cache_sr_zones`) and `ml/learner.py` (`_WATCHLIST`).

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
