# Claude Stock

Offline US stock technical analysis tool. Downloads OHLCV data from Yahoo Finance, computes technical indicators across multiple timeframes, and evaluates 12 configurable signal rules — all stored locally in SQLite. No API keys required.

## Features

- **Incremental fetching** — only downloads bars newer than what's already stored
- **4 timeframes** — 1H, 1D, 1W, 1M
- **25+ indicators** — SMA/EMA, MACD, ADX, RSI, Stochastic, Bollinger Bands, ATR, Keltner Channel, OBV, VWAP, Pivot Points, 52-week range
- **12 signal rules** — RSI oversold/overbought, Golden/Death Cross, MACD crossovers, BB squeeze/breakout, volume spike, near 52W high/low
- **Terminal + HTML reports** — color-coded tables via `rich`, static HTML via Jinja2
- **Local browser UI** — Flask app to browse all stored data

---

## Setup

**Requirements:** Python 3.12, [pyenv](https://github.com/pyenv/pyenv) + [pyenv-virtualenv](https://github.com/pyenv/pyenv-virtualenv)

```bash
# Clone and enter the project
git clone <repo-url> claude_stock
cd claude_stock

# Create and activate the virtualenv
pyenv virtualenv 3.12.9 claude-stock
pyenv local claude-stock          # writes .python-version
pip install -r requirements.txt
```

Edit `config.yaml` to set your watchlist and preferences before the first run.

---

## Quick Start

```bash
# 1. Backfill 2 years of history for all watchlist symbols
python cli.py backfill --years 2

# 2. Run the full daily pipeline (fetch → indicators → signals → report)
python cli.py run

# 3. Browse all stored data in a local web UI
python cli.py serve --port 8080
```

---

## CLI Reference

All commands accept two global flags:

| Flag | Description |
|---|---|
| `--config PATH` | Path to config YAML (default: `config.yaml`) |
| `--verbose` | Set log level to DEBUG |
| `--dry-run` | Run without writing anything to the database |

---

### `run` — Full pipeline

Fetches new bars, recomputes indicators, evaluates signals, and prints a report.

```bash
# Daily run — incremental, all symbols and timeframes
python cli.py run

# Limit to specific symbols and timeframes
python cli.py run --symbols AAPL NVDA --timeframes 1D 1W

# Force a full re-download of all history
python cli.py run --force-refetch

# Pipeline only, suppress terminal and HTML output
python cli.py run --no-report

# Preview what would be written without touching the DB
python cli.py run --dry-run
```

---

### `fetch` — Download OHLCV data

```bash
# Incremental fetch for all symbols
python cli.py fetch

# Fetch a single symbol, daily only
python cli.py fetch --symbols TSLA --timeframes 1D

# Fetch everything from a specific date
python cli.py fetch --since 2024-01-01

# Force full re-download (ignores fetch_log)
python cli.py fetch --force
```

---

### `indicators` — Compute technical indicators

```bash
# Recompute all indicators from stored OHLCV
python cli.py indicators

# Only trend and momentum indicators for AAPL
python cli.py indicators --symbols AAPL --categories trend momentum

# Recalculate every row (not just new ones)
python cli.py indicators --recalculate
```

Available categories: `trend`, `momentum`, `volatility`, `volume`, `support_resistance`

---

### `signals` — Evaluate or query signals

```bash
# Evaluate rules against the latest stored indicators
python cli.py signals

# Only for specific symbols and timeframes
python cli.py signals --symbols AAPL MSFT --timeframes 1D

# Query signals stored in the DB for a date range
python cli.py signals --since 2024-01-08 --severity warning alert

# Export to JSON
python cli.py signals --date 2024-01-15 --output-format json

# Pipe JSON to a file
python cli.py signals --since 2024-01-01 --output-format json > signals.json
```

---

### `report` — Generate reports from stored signals

```bash
# Terminal report for today's signals
python cli.py report

# HTML report for a specific date range
python cli.py report --format html --since 2024-01-08 --date 2024-01-15

# Both terminal and HTML
python cli.py report --format terminal html

# Write HTML to a custom directory
python cli.py report --format html --output-dir /tmp/reports/
```

HTML reports are written to `reports/output/report_YYYY-MM-DD.html` by default.

---

### `watchlist` — Manage tracked symbols

```bash
# Add a new symbol
python cli.py watchlist add TSLA --name "Tesla Inc." --sector Automotive

# Re-activate a previously removed symbol
python cli.py watchlist add TSLA

# Remove a symbol (soft delete — data is kept)
python cli.py watchlist remove TSLA

# List all symbols (active and inactive)
python cli.py watchlist list

# List only active symbols
python cli.py watchlist list --active-only

# Import symbols from a plain-text file (one symbol per line)
python cli.py watchlist import tickers.txt
```

After adding a new symbol, backfill its history:
```bash
python cli.py watchlist add TSLA --name "Tesla Inc." --sector Automotive
python cli.py backfill --symbols TSLA --years 2
```

---

### `status` — Database summary

```bash
# Show all symbols and timeframes in the DB
python cli.py status

# Filter to specific symbols
python cli.py status --symbols AAPL NVDA
```

Example output:

```
           DB Status
┌────────┬───────────┬──────────────────────┬───────────┬──────────────────────────────┐
│ Symbol │ Timeframe │ Last Bar             │ Row Count │ Last Signal                  │
├────────┼───────────┼──────────────────────┼───────────┼──────────────────────────────┤
│ AAPL   │ 1D        │ 2024-01-15 00:00:00  │ 503       │ RSI_OVERSOLD (2024-01-10, …) │
│ AAPL   │ 1H        │ 2024-01-15 15:00:00  │ 3521      │ —                            │
│ NVDA   │ 1D        │ 2024-01-15 00:00:00  │ 503       │ DEATH_CROSS (2024-01-14, …)  │
└────────┴───────────┴──────────────────────┴───────────┴──────────────────────────────┘
```

---

### `backfill` — Full history download

```bash
# Backfill 2 years for all watchlist symbols (default)
python cli.py backfill

# Backfill 5 years for a specific symbol
python cli.py backfill --symbols TSLA --years 5

# Preview without writing
python cli.py backfill --dry-run
```

Note: Yahoo Finance provides up to ~730 days of hourly (1H) data. Longer `--years` values only affect 1D/1W/1M timeframes for hourly bars.

---

### `serve` — Local browser UI

```bash
python cli.py serve
# → http://127.0.0.1:8080

python cli.py serve --host 0.0.0.0 --port 9000
```

---

## Browser UI

The web UI provides read-only access to all stored data. Start it with `python cli.py serve` and open `http://localhost:8080`.

### Dashboard (`/`)

Overview of the entire database — one row per `(symbol, timeframe)` with last bar date and row count, plus the 20 most recent signals across all symbols.

### OHLCV Browser (`/ohlcv`)

Browse raw price and volume data. Filter by symbol, timeframe, and date range. Results are paginated at 100 rows per page, newest first.

```
http://localhost:8080/ohlcv?symbol=AAPL&timeframe=1D&start=2024-01-01&end=2024-03-31
```

### Indicators Browser (`/indicators`)

Pivot-table view of computed indicator values — one row per bar, one column per indicator. Use the checkbox list to select specific indicators; leaving all unchecked shows every stored indicator for that symbol/timeframe.

```
http://localhost:8080/indicators?symbol=NVDA&timeframe=1D&names=RSI_14&names=SMA_50&names=BB_UPPER
```

### Signals Browser (`/signals`)

Full signal history with filters for symbol, timeframe, severity, and date range.

```
http://localhost:8080/signals?severity=alert&severity=warning&start=2024-01-01
```

---

## Configuration (`config.yaml`)

Key sections:

```yaml
watchlist:
  - symbol: AAPL
    name: Apple Inc.
    sector: Technology

data:
  timeframes: [1H, 1D, 1W, 1M]
  initial_history_days: 730   # days of 1D/1W/1M history on first run
  initial_history_hours: 60   # days of 1H history on first run
  db_path: db/stock_data.db

signals:
  enabled: true
  timeframes: [1H, 1D, 1W]   # timeframes to evaluate signals on
  rules:
    rsi_oversold:
      enabled: true
      threshold: 30
      severity: warning       # info | warning | alert

output:
  html_report:
    enabled: true
    output_dir: reports/output/
    auto_open: false
```

Config is validated on every startup. Invalid values produce a specific error message and exit code 1.

---

## Cron Setup

Run the full pipeline automatically every weekday at 4:30 PM ET:

```cron
30 21 * * 1-5 cd /path/to/claude_stock && /data/pyenv/versions/claude-stock/bin/python cli.py run >> logs/cron.log 2>&1
```

Adjust the UTC offset for DST (21:30 UTC = 4:30 PM ET in winter; use 20:30 UTC in summer).

---

## Development

```bash
# Run tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=term-missing

# Type check
mypy .
```

### Project structure

```
claude_stock/
├── cli.py                    # Entry point — argparse subcommands
├── config.yaml               # Watchlist and settings
├── data/
│   ├── models.py             # SQLAlchemy ORM (5 tables)
│   ├── storage.py            # StorageManager — central data access
│   ├── fetcher.py            # yfinance wrapper, incremental logic
│   └── watchlist.py          # Watchlist CRUD
├── indicators/
│   ├── trend.py              # SMA, EMA, MACD, ADX
│   ├── momentum.py           # RSI, Stochastic, ROC, Williams %R
│   ├── volatility.py         # Bollinger Bands, ATR, Keltner Channel
│   ├── volume.py             # OBV, VWAP, Volume SMA ratio
│   └── support_resistance.py # Pivot Points, 52-week high/low
├── signals/
│   ├── rules.py              # 12 signal rule functions
│   └── engine.py             # IndicatorRunner + SignalEngine
├── reports/
│   ├── terminal.py           # rich-based terminal output
│   ├── html_report.py        # Jinja2 HTML report generator
│   └── templates/
│       └── report.html.j2
├── server/
│   ├── app.py                # Flask routes
│   └── templates/            # base, dashboard, ohlcv, indicators, signals
├── db/                       # SQLite database (git-ignored)
├── logs/                     # Rotating log files (git-ignored)
└── tests/
```
