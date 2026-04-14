# Offline American Stock Technical Analysis Tool — Specification

## 1. Overview

A Python CLI tool that runs daily after market close (4:00–4:30 PM ET) and performs three operations in sequence:

1. **Fetch** — Download latest OHLCV data for a watchlist of US stocks from `yfinance` and store locally
2. **Indicators** — Calculate technical indicators across multiple timeframes and persist to local storage
3. **Signals** — Evaluate signal rules against the latest indicator values and issue reminders

All state is stored locally (SQLite). No cloud dependency. No API keys required.

---

## 2. Project File Structure

```
claude_stock/
├── cli.py                          # Entry point, argparse subcommands
├── config.yaml                     # User-editable watchlist + settings
├── requirements.txt
├── setup.py
│
├── data/
│   ├── __init__.py
│   ├── fetcher.py                  # yfinance download wrapper, incremental logic
│   ├── storage.py                  # StorageManager — central data access layer
│   ├── models.py                   # SQLAlchemy ORM models (5 tables)
│   └── watchlist.py                # Watchlist CRUD helpers
│
├── indicators/
│   ├── __init__.py
│   ├── base.py                     # Abstract BaseIndicator class
│   ├── trend.py                    # SMA, EMA, MACD, ADX
│   ├── momentum.py                 # RSI, Stochastic, ROC, Williams %R
│   ├── volatility.py               # Bollinger Bands, ATR, Keltner Channel
│   ├── volume.py                   # OBV, VWAP, Volume SMA ratio
│   └── support_resistance.py       # Pivot Points, 52-week high/low proximity
│
├── signals/
│   ├── __init__.py
│   ├── engine.py                   # SignalEngine — orchestrates rule evaluation
│   └── rules.py                    # Individual signal rule functions (12 rules)
│
├── reports/
│   ├── __init__.py
│   ├── terminal.py                 # rich-based pretty-printer
│   ├── html_report.py              # Jinja2 HTML report generator
│   └── templates/
│       └── report.html.j2          # Jinja2 HTML template
│
├── server/
│   ├── __init__.py
│   ├── app.py                      # Flask app — route handlers
│   └── templates/
│       ├── base.html               # Shared layout (nav, minimal CSS)
│       ├── dashboard.html          # / — watchlist overview + recent signals
│       ├── ohlcv.html              # /ohlcv — price/volume table browser
│       ├── indicators.html         # /indicators — indicator values table
│       └── signals.html            # /signals — signal history browser
│
├── db/
│   └── stock_data.db               # Auto-created SQLite file (gitignore this)
│
├── logs/
│   └── stock_tool.log              # Rotating log file (gitignore this)
│
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_fetcher.py
    ├── test_indicators.py
    ├── test_signals.py
    └── fixtures/
        └── sample_ohlcv.csv        # 300 rows of static AAPL data, no network in tests
```

---

## 3. Database Schema (SQLite via SQLAlchemy)

### 3.1 `ohlcv` — Raw price/volume data

```sql
CREATE TABLE ohlcv (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT      NOT NULL,
    timeframe       TEXT      NOT NULL,   -- '1H', '1D', '1W', '1M'
    datetime        TIMESTAMP NOT NULL,   -- for 1H: full timestamp; for 1D/1W/1M: date at 00:00:00
    open            REAL    NOT NULL,
    high            REAL    NOT NULL,
    low             REAL    NOT NULL,
    close           REAL    NOT NULL,
    volume          INTEGER NOT NULL,
    adjusted_close  REAL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, timeframe, datetime)
);
CREATE INDEX idx_ohlcv_symbol_timeframe_datetime ON ohlcv (symbol, timeframe, datetime);
```

### 3.2 `indicators` — Computed indicator values

```sql
CREATE TABLE indicators (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT      NOT NULL,
    timeframe       TEXT      NOT NULL,
    datetime        TIMESTAMP NOT NULL,
    indicator_name  TEXT      NOT NULL,  -- e.g. 'SMA_20', 'RSI_14', 'BB_UPPER'
    value           REAL,                -- NULL during warmup period
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, timeframe, datetime, indicator_name)
);
CREATE INDEX idx_indicators_symbol_timeframe ON indicators (symbol, timeframe, datetime);
```

### 3.3 `signals` — Triggered signal events

```sql
CREATE TABLE signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT      NOT NULL,
    signal_name     TEXT      NOT NULL,
    timeframe       TEXT      NOT NULL,
    datetime        TIMESTAMP NOT NULL,
    current_value   REAL,
    threshold       REAL,
    severity        TEXT      NOT NULL,  -- 'info', 'warning', 'alert'
    message         TEXT,
    acknowledged    INTEGER   DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, signal_name, timeframe, datetime)
);
CREATE INDEX idx_signals_date ON signals (date);
CREATE INDEX idx_signals_severity ON signals (severity);
```

### 3.4 `watchlist` — Tracked symbols

```sql
CREATE TABLE watchlist (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL UNIQUE,
    name        TEXT,
    sector      TEXT,
    active      INTEGER DEFAULT 1,
    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.5 `fetch_log` — Incremental fetch tracking

```sql
CREATE TABLE fetch_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT    NOT NULL,
    timeframe   TEXT    NOT NULL,
    last_datetime  TIMESTAMP NOT NULL,     -- last successfully stored bar datetime
    fetched_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (symbol, timeframe)
);
```

`fetch_log` drives incremental updates: before fetching, query `last_datetime` for each `(symbol, timeframe)` pair and request only bars after that timestamp from yfinance.

---

## 4. Configuration File (`config.yaml`)

```yaml
# ── Watchlist ─────────────────────────────────────────────────────────────────
watchlist:
  - symbol: AAPL
    name: Apple Inc.
    sector: Technology
  - symbol: MSFT
    name: Microsoft Corp.
    sector: Technology
  - symbol: NVDA
    name: NVIDIA Corp.
    sector: Semiconductors
  - symbol: SPY
    name: S&P 500 ETF
    sector: ETF
  - symbol: QQQ
    name: Nasdaq 100 ETF
    sector: ETF

# ── Data Settings ─────────────────────────────────────────────────────────────
data:
  timeframes: [1H, 1D, 1W, 1M]
  initial_history_days: 730       # days of history for 1D/1W/1M on first run
  initial_history_hours: 60       # days of hourly bars to fetch on first run (yfinance 1H limit: ~730 days)
  db_path: db/stock_data.db
  timezone: America/New_York

# ── Indicator Settings ────────────────────────────────────────────────────────
indicators:
  trend:
    sma_periods: [20, 50, 200]
    ema_periods: [9, 21]
    macd:
      fast: 12
      slow: 26
      signal: 9
    adx_period: 14

  momentum:
    rsi_period: 14
    stochastic:
      k_period: 14
      d_period: 3
      smooth_k: 3
    roc_period: 12
    williams_r_period: 14

  volatility:
    bollinger_bands:
      period: 20
      std_dev: 2.0
    atr_period: 14
    keltner_channel:
      ema_period: 20
      atr_period: 10
      multiplier: 2.0

  volume:
    obv: true
    vwap: true                    # daily timeframe only
    volume_sma_period: 20

  support_resistance:
    pivot_type: standard          # 'standard' | 'fibonacci' | 'woodie'
    week_high_low_periods: 52

# ── Signal Settings ───────────────────────────────────────────────────────────
signals:
  enabled: true
  timeframes: [1H, 1D, 1W]

  rules:
    rsi_oversold:
      enabled: true
      threshold: 30
      severity: warning

    rsi_overbought:
      enabled: true
      threshold: 70
      severity: warning

    golden_cross:
      enabled: true
      fast_period: 50
      slow_period: 200
      severity: alert

    death_cross:
      enabled: true
      fast_period: 50
      slow_period: 200
      severity: alert

    macd_bullish_crossover:
      enabled: true
      severity: info

    macd_bearish_crossover:
      enabled: true
      severity: info

    near_52w_high:
      enabled: true
      proximity_pct: 5.0
      severity: info

    near_52w_low:
      enabled: true
      proximity_pct: 5.0
      severity: alert

    bb_squeeze:
      enabled: true
      bandwidth_threshold: 0.05   # BB_WIDTH / BB_MIDDLE < 5%
      severity: info

    bb_breakout_upper:
      enabled: true
      severity: warning

    bb_breakout_lower:
      enabled: true
      severity: warning

    volume_spike:
      enabled: true
      multiplier: 2.0             # volume > 2× 20-period SMA
      severity: info

# ── Output Settings ───────────────────────────────────────────────────────────
output:
  terminal:
    enabled: true
    color_theme: dark             # 'dark' | 'light'
    show_all_indicators: false    # if false, show only triggered signals
    table_style: rounded

  html_report:
    enabled: true
    output_dir: reports/output/
    filename_template: "report_{date}.html"
    auto_open: false

  logging:
    enabled: true
    log_dir: logs/
    log_file: stock_tool.log
    level: INFO                   # DEBUG | INFO | WARNING | ERROR
    max_bytes: 10485760           # 10 MB
    backup_count: 5
```

Config is validated on startup; invalid values cause exit code 1 with a specific error message.

---

## 5. CLI Interface (`cli.py`)

Entry point uses `argparse` with subcommands.

### Global flags

```
python cli.py [--config PATH] [--verbose] [--dry-run] <subcommand> [options]
```

| Flag | Default | Description |
|---|---|---|
| `--config` | `config.yaml` | Path to config YAML |
| `--verbose` | off | Set log level to DEBUG |
| `--dry-run` | off | Run without writing to DB |

### Subcommands

#### `run` — Full pipeline
```
python cli.py run [--symbols AAPL MSFT] [--timeframes 1D 1W] [--no-report] [--force-refetch]
```

#### `fetch` — Data ingestion only
```
python cli.py fetch [--symbols AAPL] [--timeframes 1D] [--since 2024-01-01] [--force]
```

#### `indicators` — Compute from stored OHLCV
```
python cli.py indicators [--symbols AAPL] [--timeframes 1D] [--categories trend momentum] [--recalculate]
```

#### `signals` — Evaluate signal rules
```
python cli.py signals [--symbols AAPL] [--timeframes 1D] [--severity warning alert]
                      [--date 2024-01-15] [--since DATE] [--output-format terminal|json]
```

#### `report` — Generate reports from stored signals
```
python cli.py report [--format terminal html] [--date 2024-01-15] [--since DATE] [--output-dir PATH]
```

#### `watchlist` — Manage ticker watchlist
```
python cli.py watchlist add TSLA --name "Tesla Inc." --sector Automotive
python cli.py watchlist remove TSLA
python cli.py watchlist list [--active-only]
python cli.py watchlist import tickers.txt
```

#### `status` — DB summary
```
python cli.py status [--symbols AAPL]
```
Output: table showing symbol, timeframe, last fetch date, row count, last signal.

#### `backfill` — Full history for new symbols
```
python cli.py backfill [--symbols TSLA] [--years 5]
```

#### `serve` — Start the browser UI
```
python cli.py serve [--host 127.0.0.1] [--port 8080]
```
Opens a local HTTP server for browsing stored data. Intended for local use only — no authentication.

---

## 6. Data Layer

### `data/fetcher.py` — `YFinanceFetcher`

**Timeframe mapping** (internal → yfinance interval):
- `1H` → `1h`
- `1D` → `1d`
- `1W` → `1wk`
- `1M` → `1mo`

**yfinance 1H constraint:** hourly bars are available for up to ~730 days back. `initial_history_hours` (default 60 days) controls the backfill window to keep the initial fetch fast; users can increase it up to the yfinance limit.

**Incremental fetch algorithm:**
1. Query `fetch_log` for `(symbol, timeframe)` → `last_datetime`
2. If no record: use `today - initial_history_days` (or `initial_history_hours` for `1H`)
3. If `last_datetime` is the current bar or later: skip
4. Set `start = last_datetime + 1 period` (1 hour for `1H`; 1 day for others)
5. Download from yfinance
6. Normalize columns: `[open, high, low, close, volume, adjusted_close]`, DatetimeIndex (tz-aware ET, then stripped to tz-naive)
7. UPSERT into `ohlcv` (INSERT OR REPLACE on unique constraint)
8. Update `fetch_log.last_datetime`

**Error handling:**
- Retry on network timeout (max 3 retries, exponential backoff)
- Log and skip symbol on persistent failure; do not abort full run
- If yfinance returns no data (holiday/weekend): do not update `fetch_log`

### `data/storage.py` — `StorageManager`

Central data access layer shared by all modules.

```python
class StorageManager:
    def upsert_ohlcv(records: list[dict]) -> int
    def upsert_indicators(records: list[dict]) -> int
    def upsert_signals(records: list[dict]) -> int
    def get_ohlcv(symbol, timeframe, start_dt, end_dt) -> pd.DataFrame
    def get_indicators(symbol, timeframe, dt, names=None) -> pd.DataFrame
    def get_signals(dt=None, severity=None, symbols=None) -> list[Signal]
    def get_last_fetch_datetime(symbol, timeframe) -> datetime | None
    def update_fetch_log(symbol, timeframe, last_datetime)
```

All writes use `INSERT OR REPLACE` semantics (upsert on unique constraints).

### `data/models.py`

SQLAlchemy ORM models (declarative base) for all 5 tables: `OHLCV`, `Indicator`, `Signal`, `WatchlistEntry`, `FetchLog`.

Tables are auto-created on first run via `Base.metadata.create_all(engine)`.

---

## 7. Indicator Modules

### `indicators/base.py` — Abstract `BaseIndicator`

```python
class BaseIndicator(ABC):
    def __init__(self, config: dict): ...

    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Input:  OHLCV DataFrame with [open, high, low, close, volume], DatetimeIndex
        Output: DataFrame with indicator columns appended
        Column naming: INDICATOR_PARAM (e.g. SMA_20, RSI_14, BB_UPPER)
        Warmup rows: NaN (stored as NULL in DB)
        """

    def validate_input(self, df: pd.DataFrame) -> None:
        """Raises ValueError if df lacks required columns or has too few rows."""
```

### Indicator library: `pandas-ta` (pure Python, no C dependency)

### `indicators/trend.py`

| Indicator | Output columns | Min rows |
|---|---|---|
| SMA(20/50/200) | `SMA_20`, `SMA_50`, `SMA_200` | 200 |
| EMA(9/21) | `EMA_9`, `EMA_21` | 21 |
| MACD(12,26,9) | `MACD_LINE`, `MACD_SIGNAL`, `MACD_HIST` | 35 |
| ADX(14) | `ADX_14`, `DI_PLUS_14`, `DI_MINUS_14` | 28 |

### `indicators/momentum.py`

| Indicator | Output columns | Range |
|---|---|---|
| RSI(14) | `RSI_14` | 0–100 |
| Stochastic(14,3,3) | `STOCH_K`, `STOCH_D` | 0–100 |
| ROC(12) | `ROC_12` | % |
| Williams %R(14) | `WILLR_14` | -100 to 0 |

### `indicators/volatility.py`

| Indicator | Output columns |
|---|---|
| Bollinger Bands(20, 2σ) | `BB_UPPER`, `BB_MIDDLE`, `BB_LOWER`, `BB_WIDTH`, `BB_PCT_B` |
| ATR(14) | `ATR_14` |
| Keltner Channel | `KC_UPPER`, `KC_MIDDLE`, `KC_LOWER` |

`BB_WIDTH = (BB_UPPER - BB_LOWER) / BB_MIDDLE`

### `indicators/volume.py`

| Indicator | Output columns | Notes |
|---|---|---|
| OBV | `OBV` | |
| VWAP | `VWAP` | 1H and 1D only; NULL for 1W/1M |
| Volume SMA ratio | `VOL_SMA_20`, `VOL_RATIO` | `VOL_RATIO = volume / VOL_SMA_20` |

### `indicators/support_resistance.py`

| Indicator | Output columns | Notes |
|---|---|---|
| Pivot Points | `PP`, `R1`, `R2`, `R3`, `S1`, `S2`, `S3` | Uses prior period H/L/C |
| 52-week range | `HIGH_52W`, `PCT_FROM_52W_HIGH`, `LOW_52W`, `PCT_FROM_52W_LOW` | Rolling 52-week window |

**Adjusted close usage:** All price-based indicators use `adjusted_close`. Raw `close` is stored for reference but not used in calculations. VWAP uses raw OHLCV (unadjusted). Note: yfinance does not provide adjusted close for the `1H` timeframe — `adjusted_close` is stored as `NULL` for hourly bars, and raw `close` is used for 1H indicator calculations instead.

**Warmup handling:** Symbols with fewer than 200 rows skip `SMA_200` and log a warning. Other indicators with shorter lookbacks are still computed.

---

## 8. Signal Engine

### `signals/rules.py` — Rule functions

Each rule is a standalone function with a uniform signature:

```python
def rule_<name>(
    symbol: str,
    timeframe: str,
    date: date,
    indicators: dict[str, float],      # current row: {indicator_name: value}
    prev_indicators: dict[str, float], # prior row (for crossover detection)
    config: dict
) -> Signal | None:
    """Returns Signal if triggered, None otherwise."""
```

### Signal rules (12 total)

| Rule function | Signal name | Trigger condition | Default severity |
|---|---|---|---|
| `rule_rsi_oversold` | `RSI_OVERSOLD` | RSI_14 < 30 | warning |
| `rule_rsi_overbought` | `RSI_OVERBOUGHT` | RSI_14 > 70 | warning |
| `rule_golden_cross` | `GOLDEN_CROSS` | SMA_50 crosses above SMA_200 | alert |
| `rule_death_cross` | `DEATH_CROSS` | SMA_50 crosses below SMA_200 | alert |
| `rule_macd_bullish_crossover` | `MACD_BULLISH_XOVER` | MACD_LINE crosses above MACD_SIGNAL | info |
| `rule_macd_bearish_crossover` | `MACD_BEARISH_XOVER` | MACD_LINE crosses below MACD_SIGNAL | info |
| `rule_near_52w_high` | `NEAR_52W_HIGH` | PCT_FROM_52W_HIGH ≤ 5% | info |
| `rule_near_52w_low` | `NEAR_52W_LOW` | PCT_FROM_52W_LOW ≤ 5% | alert |
| `rule_bb_squeeze` | `BB_SQUEEZE` | BB_WIDTH / BB_MIDDLE < 0.05 | info |
| `rule_bb_breakout_upper` | `BB_BREAKOUT_UP` | close > BB_UPPER | warning |
| `rule_bb_breakout_lower` | `BB_BREAKOUT_DOWN` | close < BB_LOWER | warning |
| `rule_volume_spike` | `VOLUME_SPIKE` | VOL_RATIO > 2.0 | info |

**Crossover detection:** Current row's value crossed if `today_val > threshold AND yesterday_val <= threshold` (or vice versa). Engine always fetches at least 2 consecutive rows and passes both to rule functions.

### `signals/engine.py` — `SignalEngine`

```
Algorithm:
  for each symbol in watchlist:
    for each timeframe in config.signals.timeframes:
      df = merge(get_ohlcv, get_indicators) for last N rows
      for each date row (typically just latest):
        for each enabled rule:
          signal = rule_fn(symbol, timeframe, date,
                           indicators[i], indicators[i-1], config)
          if signal: upsert_signal(signal), collect
  return all_signals
```

---

## 9. Signal Data Structure

```python
@dataclass
class Signal:
    symbol: str           # e.g. "AAPL"
    signal_name: str      # e.g. "RSI_OVERSOLD"
    timeframe: str        # e.g. "1H", "1D"
    datetime: datetime    # e.g. 2024-01-15 14:00:00 (1H) or 2024-01-15 00:00:00 (1D)
    current_value: float  # e.g. 28.4
    threshold: float      # e.g. 30.0
    severity: str         # "info" | "warning" | "alert"
    message: str          # human-readable description
```

---

## 10. Output Formats

### Terminal (via `rich`)

Signals grouped by severity (alerts first), then by symbol. Color coding: alert = bold red, warning = bold yellow, info = cyan.

```
╭──────────────────────────────────────────────────────────────────────────╮
│          Stock Signal Report — 2024-01-15 (after market close)          │
╰──────────────────────────────────────────────────────────────────────────╯

 ALERTS (2)
┌────────┬──────────────┬───────────┬───────────────┬───────────┬─────────┐
│ Symbol │ Signal       │ Timeframe │ Current Value │ Threshold │ Date    │
├────────┼──────────────┼───────────┼───────────────┼───────────┼─────────┤
│ AAPL   │ NEAR_52W_LOW │ 1D        │ 2.3% away     │ 5.0%      │ Jan 15  │
│ NVDA   │ DEATH_CROSS  │ 1W        │ SMA50=412.3   │ SMA200=   │ Jan 14  │
│        │              │           │               │ 445.1     │         │
└────────┴──────────────┴───────────┴───────────────┴───────────┴─────────┘

 WARNINGS (2)
 ...

 INFO (4)
 ...

 Summary: 8 signals across 4 symbols | Run time: 11.2s | DB: db/stock_data.db
```

### JSON (via `--output-format json`)

```json
[
  {
    "symbol": "AAPL",
    "signal_name": "RSI_OVERSOLD",
    "timeframe": "1D",
    "date": "2024-01-15",
    "current_value": 28.4,
    "threshold": 30.0,
    "severity": "warning",
    "message": "AAPL RSI=28.4 below oversold threshold 30 on 1D"
  }
]
```

### HTML Report (via Jinja2 + Chart.js)

File: `reports/output/report_2024-01-15.html`

Contents:
- Header with date and run metadata
- Summary stats (total signals, by severity, by symbol)
- Three collapsible sections (Alerts / Warnings / Info), each as a sortable HTML table
- Mini sparkline charts per triggered symbol (Chart.js from CDN)
- Footer with run duration and DB path

---

## 11. Browser UI (`server/`)

A lightweight Flask app for exploring stored data locally. No JavaScript frameworks, no build step. All pages are plain HTML tables with a minimal inline stylesheet. Navigation via `<a>` links and HTML `<form>` GET requests — no AJAX.

### Design principles

- **Plain HTML only** — `<table>`, `<form>`, `<select>`, `<input>`. No JS libraries.
- **GET forms** — all filters are query parameters so URLs are bookmarkable.
- **Accurate numbers** — raw values from DB, formatted to a fixed number of decimal places per column type; no rounding beyond display.
- **Pagination** — 100 rows per page for OHLCV and indicators; `?page=N` query param.
- **Read-only** — the server never writes to the DB.

### Routes

| Route | Page | Query params |
|---|---|---|
| `GET /` | Dashboard | — |
| `GET /ohlcv` | OHLCV browser | `symbol`, `timeframe`, `start`, `end`, `page` |
| `GET /indicators` | Indicators browser | `symbol`, `timeframe`, `start`, `end`, `names` (multi-select), `page` |
| `GET /signals` | Signals browser | `symbol`, `timeframe`, `severity`, `start`, `end`, `page` |

### `server/app.py`

```python
from flask import Flask, render_template, request, g
from data.storage import StorageManager

app = Flask(__name__)

def get_storage() -> StorageManager:
    if "storage" not in g:
        g.storage = StorageManager(app.config["DB_PATH"])
    return g.storage

@app.teardown_appcontext
def close_storage(exc):
    storage = g.pop("storage", None)
    if storage:
        storage.close()

@app.route("/")
def dashboard(): ...

@app.route("/ohlcv")
def ohlcv(): ...

@app.route("/indicators")
def indicators(): ...

@app.route("/signals")
def signals(): ...
```

Started from `cli.py serve` as:
```python
app.config["DB_PATH"] = config["data"]["db_path"]
app.run(host=args.host, port=args.port, debug=False)
```

### Page details

#### `/` — Dashboard

Two sections, no forms:

**Watchlist status table** — one row per `(symbol, timeframe)`:

| Symbol | Name | Timeframe | Last Bar | Row Count | Last Signal |
|---|---|---|---|---|---|
| AAPL | Apple Inc. | 1D | 2024-01-15 | 503 | RSI_OVERSOLD (Jan 10, warning) |
| AAPL | Apple Inc. | 1H | 2024-01-15 14:00 | 3521 | — |

**Recent signals table** — last 20 signals across all symbols, newest first:

| Datetime | Symbol | Timeframe | Signal | Value | Threshold | Severity |
|---|---|---|---|---|---|---|
| 2024-01-15 | AAPL | 1D | RSI_OVERSOLD | 28.4 | 30.0 | warning |

#### `/ohlcv` — OHLCV Browser

Filter form (GET, same page):
```
Symbol: [dropdown of watchlist symbols]   Timeframe: [1H|1D|1W|1M]
Start: [date input]   End: [date input]   [Apply]
```

Results table (100 rows/page, newest first):

| Datetime | Open | High | Low | Close | Adj Close | Volume |
|---|---|---|---|---|---|---|
| 2024-01-15 | 185.23 | 186.40 | 184.90 | 185.85 | 185.85 | 52,341,200 |

Numbers: prices to 2 dp, volume with thousands separator, adj close to 4 dp.

Pagination: `« Prev  Page 3 of 18  Next »` links at bottom.

#### `/indicators` — Indicators Browser

Filter form:
```
Symbol: [dropdown]   Timeframe: [dropdown]
Start: [date]   End: [date]
Indicators: [multi-select checkbox list of all stored indicator names]   [Apply]
```

Results table — one row per bar, one column per selected indicator (newest first):

| Datetime | SMA_20 | SMA_50 | RSI_14 | MACD_LINE | BB_UPPER | … |
|---|---|---|---|---|---|---|
| 2024-01-15 | 182.41 | 178.30 | 28.4 | -0.23 | 191.20 | … |

Null values displayed as `—`. Numbers to 4 dp for indicator values. If no indicators are selected, all stored indicators for that symbol+timeframe are shown.

#### `/signals` — Signals Browser

Filter form:
```
Symbol: [dropdown, "All"]   Timeframe: [dropdown, "All"]
Severity: [checkboxes: alert | warning | info]
Start: [date]   End: [date]   [Apply]
```

Results table (newest first):

| Datetime | Symbol | Timeframe | Signal | Current Value | Threshold | Severity | Message |
|---|---|---|---|---|---|---|---|
| 2024-01-15 | AAPL | 1D | RSI_OVERSOLD | 28.40 | 30.00 | warning | AAPL RSI=28.4 … |

Severity rendered as text with inline color: `alert` = red, `warning` = orange, `info` = teal (via `style="color:…"` — no CSS class needed).

### `server/templates/base.html`

Minimal shared layout:

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Stock Tool — {{ title }}</title>
  <style>
    body { font-family: monospace; max-width: 1400px; margin: 0 auto; padding: 1rem; }
    nav a { margin-right: 1.5rem; }
    table { border-collapse: collapse; width: 100%; font-size: 0.9rem; }
    th, td { border: 1px solid #ccc; padding: 4px 8px; text-align: right; }
    th { background: #f0f0f0; text-align: center; }
    td:first-child { text-align: left; }
    tr:nth-child(even) { background: #fafafa; }
    form { margin-bottom: 1rem; }
    select, input[type=date], input[type=text] { font-family: monospace; }
    .alert { color: #c00; }
    .warning { color: #a60; }
    .info { color: #077; }
    .pagination { margin-top: 0.5rem; }
  </style>
</head>
<body>
  <nav>
    <strong>Stock Tool</strong> &nbsp;|&nbsp;
    <a href="/">Dashboard</a>
    <a href="/ohlcv">OHLCV</a>
    <a href="/indicators">Indicators</a>
    <a href="/signals">Signals</a>
  </nav>
  <hr>
  <h2>{{ title }}</h2>
  {% block content %}{% endblock %}
</body>
</html>
```

No external CSS or JS. The four `.alert/.warning/.info` classes are the only named styles beyond layout basics.

---

## 12. Dependencies (`requirements.txt`)

```
# Core
yfinance>=0.2.36
pandas>=2.1.0
numpy>=1.26.0
pandas-ta>=0.3.14b

# Storage
SQLAlchemy>=2.0.0

# Configuration
pyyaml>=6.0.1

# Terminal output
rich>=13.7.0

# HTML report + browser UI
jinja2>=3.1.3
flask>=3.0.0

# Testing
pytest>=8.0.0
pytest-cov>=5.0.0

# Dev
mypy>=1.9.0
```

Note: `pandas-ta` is pure Python and covers all required indicators. `ta-lib` is not used because it requires a system-level C library install, which is fragile across environments.

---

## 12. Key Implementation Details

### Incremental Fetch

- **First run**: no `fetch_log` record → fetch `today - initial_history_days` (or `initial_history_hours` for `1H`) to now
- **Subsequent runs**: `start = fetch_log.last_datetime + 1 period` (1 hour for `1H`; 1 day otherwise)
- **Already current**: skip if `last_datetime` is the most recently closed bar
- **No data returned** (holiday/weekend/off-hours): do not update `fetch_log`; next run retries

### Weekend / Holiday Handling

If run on Saturday or Sunday, the tool processes data for the prior Friday close. Holiday detection is not built in — yfinance returns no data for market holidays, and the fetch succeeds silently (no rows inserted, `fetch_log` not updated).

### Signal Deduplication

`UNIQUE (symbol, signal_name, timeframe, datetime)` on `signals` table prevents duplicate alerts when the tool runs multiple times. On conflict: update row (threshold or config may have changed).

### Crossover Detection

Requires 2 consecutive rows. Engine fetches the most recent 2 rows per `(symbol, timeframe)`. If only 1 row exists, crossover rules are skipped with a debug log entry.

### Adjusted Close

All price-based indicator calculations use `adjusted_close` to account for splits and dividends. Raw `close` is stored for reference. VWAP uses unadjusted OHLCV since it approximates intraday VWAP on daily data.

### Warmup Period

Engine skips `SMA_200` for symbols with fewer than 200 stored rows and logs: `"AAPL 1D: insufficient history (87 rows), skipping SMA_200"`. Other indicators with shorter lookbacks are still computed.

### Config Validation

Validated checks on startup:
- Symbols: non-empty uppercase strings
- SMA periods: list of positive integers
- RSI threshold: `0 < value < 100`
- Proximity pct: `0 < value < 100`
- Volume multiplier: `> 1.0`
- Severity: one of `['info', 'warning', 'alert']`
- Timeframes: subset of `['1H', '1D', '1W', '1M']`

---

## 13. Testing Strategy

### `tests/conftest.py` fixtures

| Fixture | Description |
|---|---|
| `sample_ohlcv_df` | Loads `tests/fixtures/sample_ohlcv.csv` (300 rows AAPL, no network) |
| `in_memory_db` | Temporary SQLite `:memory:` DB + `StorageManager` instance |
| `mock_config` | Minimal config dict for fast tests |
| `mock_fetcher` | `MagicMock` wrapping `YFinanceFetcher`, returns `sample_ohlcv_df` |

### `tests/test_indicators.py`

Per indicator module:
- All expected output columns present
- Values within valid ranges (RSI 0–100, Williams %R -100 to 0)
- NaN at warmup boundaries
- Minimum viable input (exactly `min_periods` rows)
- Edge case: all-zero volume (OBV)

### `tests/test_signals.py`

Per rule function:
- Synthetic `indicators` dict that should trigger → assert `Signal` returned
- Synthetic dict that should NOT trigger → assert `None` returned
- Crossover rules: test yesterday/today pairs
- Disabled rules in config → assert `None`

### `tests/test_fetcher.py`

- Incremental date logic with mocked `fetch_log` entries
- Timeframe mapping correctness
- Retry behavior with mocked network errors
- Column normalization output

---

## 14. Implementation Sequence

| Phase | Deliverables |
|---|---|
| **1 — Foundation** | `requirements.txt`, `config.yaml`, `data/models.py`, `data/storage.py`, DB auto-init |
| **2 — Ingestion** | `data/fetcher.py` (incremental), `data/watchlist.py`, `tests/test_fetcher.py` |
| **3 — Indicators** | `indicators/base.py` + all 5 indicator modules, `tests/test_indicators.py` |
| **4 — Signals** | `signals/rules.py` (12 rules), `signals/engine.py`, `tests/test_signals.py` |
| **5 — Output & CLI** | `reports/terminal.py`, `reports/html_report.py` + template, `cli.py` all subcommands |
| **6 — Browser UI** | `server/app.py`, 4 Jinja2 templates, `cli.py serve` subcommand |
| **7 — Polish** | Logging setup, error hardening, `status` command, `.gitignore`, cron instructions |

---

## 15. Example Usage

```bash
# First-time setup: backfill 2 years of history
python cli.py backfill --years 2

# Daily run (scheduled via cron at 4:30 PM ET)
python cli.py run

# Add a new symbol
python cli.py watchlist add TSLA --name "Tesla Inc." --sector Automotive
python cli.py backfill --symbols TSLA --years 2

# View signals from the past week
python cli.py signals --since 2024-01-08 --severity warning alert

# Export signals to JSON
python cli.py signals --date 2024-01-15 --output-format json > signals.json

# Check DB status
python cli.py status

# Browse stored data in browser
python cli.py serve --port 8080
# then open http://localhost:8080
```

### Cron setup (Linux/macOS)

```cron
# Run daily at 4:30 PM ET (21:30 UTC — adjust for DST)
30 21 * * 1-5 cd /path/to/claude_stock && python cli.py run >> logs/cron.log 2>&1
```

---

## 16. Out of Scope (v1)

- Sub-hourly data (1H is the finest supported granularity)
- Options, futures, or cryptocurrency data
- Machine learning or predictive signals
- Portfolio tracking or P&L calculation
- Push notifications (email, Slack) — only terminal + HTML output in v1
- Multi-user or networked access
