#!/usr/bin/env python3
"""CLI entry point for the offline stock technical analysis tool."""
import argparse
import logging
import logging.handlers
import os
import sys
import time
from datetime import datetime

import yaml


def load_config(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def validate_config(config: dict):
    """Validate config; exit with code 1 and a specific error message on failure."""
    watchlist = config.get("watchlist", [])
    if not watchlist:
        sys.exit("Config error: watchlist is empty")
    for entry in watchlist:
        sym = entry.get("symbol", "")
        if not sym:
            sys.exit("Config error: watchlist entry is missing 'symbol'")

    valid_tfs = {"1H", "1D", "1W", "1M"}
    for tf in config.get("data", {}).get("timeframes", []):
        if tf not in valid_tfs:
            sys.exit(f"Config error: invalid timeframe '{tf}' (valid: {sorted(valid_tfs)})")

    ind = config.get("indicators", {})
    sma_periods = ind.get("trend", {}).get("sma_periods", [])
    if not all(isinstance(p, int) and p > 0 for p in sma_periods):
        sys.exit("Config error: indicators.trend.sma_periods must be a list of positive integers")

    rules = config.get("signals", {}).get("rules", {})

    for rule_name in ("rsi_oversold", "rsi_overbought"):
        threshold = rules.get(rule_name, {}).get("threshold", 30)
        if not (0 < threshold < 100):
            sys.exit(f"Config error: {rule_name}.threshold must be between 0 and 100, got {threshold}")

    for rule_name in ("near_52w_high", "near_52w_low"):
        pct = rules.get(rule_name, {}).get("proximity_pct", 5.0)
        if not (0 < pct < 100):
            sys.exit(f"Config error: {rule_name}.proximity_pct must be between 0 and 100, got {pct}")

    vol_mult = rules.get("volume_spike", {}).get("multiplier", 2.0)
    if vol_mult <= 1.0:
        sys.exit(f"Config error: volume_spike.multiplier must be > 1.0, got {vol_mult}")

    valid_severities = {"info", "warning", "alert"}
    for rule_name, rule_cfg in rules.items():
        sev = rule_cfg.get("severity", "info")
        if sev not in valid_severities:
            sys.exit(f"Config error: invalid severity '{sev}' for rule '{rule_name}'")


def setup_logging(config: dict, verbose: bool):
    """Configure root logger from config. Call once at startup."""
    log_cfg = config.get("output", {}).get("logging", {})
    if not log_cfg.get("enabled", True):
        logging.basicConfig(level=logging.WARNING)
        return

    level_str = "DEBUG" if verbose else log_cfg.get("level", "INFO")
    level = getattr(logging, level_str, logging.INFO)

    fmt = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    log_dir = log_cfg.get("log_dir", "logs/")
    log_file = log_cfg.get("log_file", "stock_tool.log")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, log_file)
    max_bytes = log_cfg.get("max_bytes", 10 * 1024 * 1024)
    backup_count = log_cfg.get("backup_count", 5)
    handlers.append(
        logging.handlers.RotatingFileHandler(
            log_path, maxBytes=max_bytes, backupCount=backup_count
        )
    )

    logging.basicConfig(level=level, format=fmt, handlers=handlers)


def get_storage(config: dict):
    from data.storage import StorageManager

    db_path = config["data"]["db_path"]
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    return StorageManager(db_path)


# ── Subcommand handlers ───────────────────────────────────────────────────────

def cmd_run(args, config):
    """Full pipeline: fetch → indicators → signals → report."""
    from data.fetcher import YFinanceFetcher
    from data.watchlist import sync_watchlist_to_db
    from signals.engine import IndicatorRunner, SignalEngine
    from reports.terminal import print_signals
    from reports.html_report import generate_report

    storage = get_storage(config)
    sync_watchlist_to_db(storage, config)

    symbols = args.symbols or None
    timeframes = args.timeframes or None
    t0 = time.time()

    fetcher = YFinanceFetcher(storage, config)
    fetcher.fetch_all(
        symbols=symbols,
        timeframes=timeframes,
        force=args.force_refetch,
        dry_run=args.dry_run,
    )

    runner = IndicatorRunner(storage, config)
    runner.run(symbols=symbols, timeframes=timeframes, dry_run=args.dry_run)

    engine = SignalEngine(storage, config)
    signals = engine.run(symbols=symbols, timeframes=timeframes, dry_run=args.dry_run)

    run_time = time.time() - t0

    if not args.no_report:
        out_cfg = config.get("output", {})
        if out_cfg.get("terminal", {}).get("enabled", True):
            print_signals(signals, run_time_s=run_time, db_path=config["data"]["db_path"])
        if out_cfg.get("html_report", {}).get("enabled", True):
            path = generate_report(signals, config, run_time_s=run_time)
            print(f"HTML report: {path}")

    storage.close()


def cmd_fetch(args, config):
    from data.fetcher import YFinanceFetcher
    from data.watchlist import sync_watchlist_to_db

    storage = get_storage(config)
    sync_watchlist_to_db(storage, config)

    fetcher = YFinanceFetcher(storage, config)
    results = fetcher.fetch_all(
        symbols=args.symbols or None,
        timeframes=args.timeframes or None,
        force=args.force,
        since=args.since,
        dry_run=args.dry_run,
    )
    total = sum(results.values())
    print(f"Fetched {total} rows across {len(results)} symbol/timeframe pairs.")
    storage.close()


def cmd_indicators(args, config):
    from signals.engine import IndicatorRunner
    from data.watchlist import sync_watchlist_to_db

    storage = get_storage(config)
    sync_watchlist_to_db(storage, config)

    runner = IndicatorRunner(storage, config)
    total = runner.run(
        symbols=args.symbols or None,
        timeframes=args.timeframes or None,
        categories=args.categories or None,
        recalculate=args.recalculate,
        dry_run=args.dry_run,
    )
    print(f"Computed {total} indicator rows.")
    storage.close()


def cmd_signals(args, config):
    from signals.engine import SignalEngine
    from data.watchlist import sync_watchlist_to_db
    from reports.terminal import print_signals
    import json

    storage = get_storage(config)
    sync_watchlist_to_db(storage, config)

    if args.date or args.since:
        # Query stored signals (no new evaluation)
        start_dt = datetime.fromisoformat(args.since) if args.since else None
        end_dt = datetime.fromisoformat(args.date) if args.date else None
        # severity filter: only single-value supported by storage layer
        sev_filter = args.severity[0] if args.severity and len(args.severity) == 1 else None
        signals = storage.get_signals(
            start_dt=start_dt,
            end_dt=end_dt,
            severity=sev_filter,
            symbols=args.symbols or None,
        )
    else:
        engine = SignalEngine(storage, config)
        signals = engine.run(
            symbols=args.symbols or None,
            timeframes=args.timeframes or None,
            dry_run=args.dry_run,
        )

    if args.output_format == "json":
        output = []
        for sig in signals:
            row = dict(sig)
            if hasattr(row.get("datetime"), "isoformat"):
                row["datetime"] = row["datetime"].isoformat()
            output.append(row)
        print(json.dumps(output, indent=2, default=str))
    else:
        print_signals(signals, db_path=config["data"]["db_path"])

    storage.close()


def cmd_report(args, config):
    from reports.terminal import print_signals
    from reports.html_report import generate_report

    storage = get_storage(config)

    start_dt = datetime.fromisoformat(args.since) if args.since else None
    end_dt = datetime.fromisoformat(args.date) if args.date else None
    signals = storage.get_signals(start_dt=start_dt, end_dt=end_dt)

    formats = args.format or ["terminal"]

    if "terminal" in formats:
        print_signals(signals, db_path=config["data"]["db_path"])

    if "html" in formats:
        if args.output_dir:
            config = dict(config)
            cfg_out = dict(config.get("output", {}))
            cfg_html = dict(cfg_out.get("html_report", {}))
            cfg_html["output_dir"] = args.output_dir
            cfg_out["html_report"] = cfg_html
            config["output"] = cfg_out
        path = generate_report(signals, config)
        print(f"HTML report: {path}")

    storage.close()


def cmd_watchlist(args, config):
    from data.watchlist import add_symbol, remove_symbol, list_symbols, sync_watchlist_to_db

    storage = get_storage(config)

    if args.watchlist_cmd == "add":
        add_symbol(storage, args.symbol.upper(), name=args.name, sector=args.sector)
        print(f"Added {args.symbol.upper()} to watchlist.")

    elif args.watchlist_cmd == "remove":
        remove_symbol(storage, args.symbol.upper())
        print(f"Removed {args.symbol.upper()} from watchlist.")

    elif args.watchlist_cmd == "list":
        entries = list_symbols(storage, active_only=args.active_only)
        if not entries:
            print("No symbols in watchlist.")
        else:
            print(f"{'Symbol':<10} {'Name':<30} {'Sector':<20} Active")
            print("-" * 65)
            for e in entries:
                print(
                    f"{e['symbol']:<10} {(e.get('name') or ''):<30}"
                    f" {(e.get('sector') or ''):<20} {e.get('active', 1)}"
                )

    elif args.watchlist_cmd == "import":
        with open(args.file) as f:
            symbols = [
                line.strip().upper()
                for line in f
                if line.strip() and not line.startswith("#")
            ]
        for sym in symbols:
            add_symbol(storage, sym)
        print(f"Imported {len(symbols)} symbols.")

    storage.close()


def cmd_status(args, config):
    from reports.terminal import print_status

    storage = get_storage(config)
    rows = storage.get_watchlist_status()

    if args.symbols:
        upper = [s.upper() for s in args.symbols]
        rows = [r for r in rows if r["symbol"] in upper]

    # Adapt to shape expected by print_status
    for r in rows:
        r["row_count"] = r.get("ohlcv_count", 0)
        sig_name = r.get("last_signal_name")
        sig_dt = r.get("last_signal_datetime")
        if sig_name:
            dt_str = str(sig_dt)[:10] if sig_dt else ""
            r["last_signal"] = f"{sig_name} ({dt_str}, {r.get('last_signal_severity', '')})"
        else:
            r["last_signal"] = "—"

    print_status(rows)
    storage.close()


def cmd_backfill(args, config):
    from data.fetcher import YFinanceFetcher
    from data.watchlist import sync_watchlist_to_db

    storage = get_storage(config)
    sync_watchlist_to_db(storage, config)

    years = args.years or 2
    days = int(years * 365)
    # yfinance 1H limit is ~730 days
    hours_days = min(days, 729)

    config = dict(config)
    config["data"] = dict(config["data"])
    config["data"]["initial_history_days"] = days
    config["data"]["initial_history_hours"] = hours_days

    fetcher = YFinanceFetcher(storage, config)
    results = fetcher.fetch_all(
        symbols=args.symbols or None,
        force=True,
        dry_run=args.dry_run,
    )
    total = sum(results.values())
    print(f"Backfill complete: {total} rows.")
    storage.close()


def cmd_serve(args, config):
    from server.app import app

    db_path = config["data"]["db_path"]
    app.config["DB_PATH"] = db_path
    print(f"Starting server at http://{args.host}:{args.port}")
    print(f"DB: {db_path}  (Ctrl-C to stop)")
    app.run(host=args.host, port=args.port, debug=False)


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Offline American stock technical analysis tool",
    )
    parser.add_argument(
        "--config", default="config.yaml", metavar="PATH",
        help="Path to config YAML (default: config.yaml)",
    )
    parser.add_argument("--verbose", action="store_true", help="Set log level to DEBUG")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing to DB")

    sub = parser.add_subparsers(dest="command", metavar="<subcommand>")
    sub.required = True

    # ── run ──────────────────────────────────────────────────────────────────
    p_run = sub.add_parser("run", help="Full pipeline: fetch + indicators + signals")
    p_run.add_argument("--symbols", nargs="+", metavar="SYMBOL")
    p_run.add_argument("--timeframes", nargs="+", metavar="TF")
    p_run.add_argument("--no-report", action="store_true", dest="no_report",
                       help="Skip terminal and HTML report output")
    p_run.add_argument("--force-refetch", action="store_true", dest="force_refetch",
                       help="Re-download full history instead of incremental update")

    # ── fetch ─────────────────────────────────────────────────────────────────
    p_fetch = sub.add_parser("fetch", help="Download OHLCV data only")
    p_fetch.add_argument("--symbols", nargs="+", metavar="SYMBOL")
    p_fetch.add_argument("--timeframes", nargs="+", metavar="TF")
    p_fetch.add_argument("--since", metavar="DATE", help="Fetch from this date (YYYY-MM-DD)")
    p_fetch.add_argument("--force", action="store_true", help="Force full refetch")

    # ── indicators ───────────────────────────────────────────────────────────
    p_ind = sub.add_parser("indicators", help="Compute indicators from stored OHLCV")
    p_ind.add_argument("--symbols", nargs="+", metavar="SYMBOL")
    p_ind.add_argument("--timeframes", nargs="+", metavar="TF")
    p_ind.add_argument(
        "--categories", nargs="+",
        choices=["trend", "momentum", "volatility", "volume", "support_resistance"],
        metavar="CAT",
    )
    p_ind.add_argument("--recalculate", action="store_true",
                       help="Recalculate all indicators (not just new rows)")

    # ── signals ──────────────────────────────────────────────────────────────
    p_sig = sub.add_parser("signals", help="Evaluate signal rules or query stored signals")
    p_sig.add_argument("--symbols", nargs="+", metavar="SYMBOL")
    p_sig.add_argument("--timeframes", nargs="+", metavar="TF")
    p_sig.add_argument("--severity", nargs="+", choices=["warning", "alert", "info"],
                       metavar="SEV")
    p_sig.add_argument("--date", metavar="DATE",
                       help="Query signals on or before this date (YYYY-MM-DD)")
    p_sig.add_argument("--since", metavar="DATE",
                       help="Query signals on or after this date (YYYY-MM-DD)")
    p_sig.add_argument("--output-format", choices=["terminal", "json"], default="terminal",
                       dest="output_format")

    # ── report ───────────────────────────────────────────────────────────────
    p_rep = sub.add_parser("report", help="Generate report from stored signals")
    p_rep.add_argument("--format", nargs="+", choices=["terminal", "html"], default=["terminal"],
                       metavar="FMT")
    p_rep.add_argument("--date", metavar="DATE",
                       help="End date for signal query (YYYY-MM-DD)")
    p_rep.add_argument("--since", metavar="DATE",
                       help="Start date for signal query (YYYY-MM-DD)")
    p_rep.add_argument("--output-dir", metavar="PATH", dest="output_dir",
                       help="Override HTML output directory")

    # ── watchlist ─────────────────────────────────────────────────────────────
    p_wl = sub.add_parser("watchlist", help="Manage ticker watchlist")
    wl_sub = p_wl.add_subparsers(dest="watchlist_cmd", metavar="<action>")
    wl_sub.required = True

    p_wl_add = wl_sub.add_parser("add", help="Add a symbol")
    p_wl_add.add_argument("symbol", help="Ticker symbol (e.g. TSLA)")
    p_wl_add.add_argument("--name", help="Company name")
    p_wl_add.add_argument("--sector", help="Sector")

    p_wl_rm = wl_sub.add_parser("remove", help="Remove (soft-delete) a symbol")
    p_wl_rm.add_argument("symbol")

    p_wl_ls = wl_sub.add_parser("list", help="List watchlist symbols")
    p_wl_ls.add_argument("--active-only", action="store_true", default=False,
                          dest="active_only",
                          help="Show only active symbols (default: show all)")

    p_wl_imp = wl_sub.add_parser("import", help="Import symbols from a text file")
    p_wl_imp.add_argument("file", help="File with one symbol per line")

    # ── status ────────────────────────────────────────────────────────────────
    p_status = sub.add_parser("status", help="Show DB summary table")
    p_status.add_argument("--symbols", nargs="+", metavar="SYMBOL")

    # ── backfill ──────────────────────────────────────────────────────────────
    p_bf = sub.add_parser("backfill", help="Full history backfill for one or more symbols")
    p_bf.add_argument("--symbols", nargs="+", metavar="SYMBOL")
    p_bf.add_argument("--years", type=float, default=2,
                      help="Years of history to fetch (default: 2)")

    # ── serve ─────────────────────────────────────────────────────────────────
    p_serve = sub.add_parser("serve", help="Start local browser UI")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8080)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not os.path.exists(args.config):
        sys.exit(f"Config file not found: {args.config}")
    config = load_config(args.config)
    validate_config(config)
    setup_logging(config, verbose=args.verbose)

    handlers = {
        "run": cmd_run,
        "fetch": cmd_fetch,
        "indicators": cmd_indicators,
        "signals": cmd_signals,
        "report": cmd_report,
        "watchlist": cmd_watchlist,
        "status": cmd_status,
        "backfill": cmd_backfill,
        "serve": cmd_serve,
    }

    handler = handlers[args.command]
    handler(args, config)


if __name__ == "__main__":
    main()
