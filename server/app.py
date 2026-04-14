import os
from flask import Flask, render_template, request, g
from data.storage import StorageManager

app = Flask(__name__, template_folder="templates")
PAGE_SIZE = 100


def get_storage() -> StorageManager:
    if "storage" not in g:
        g.storage = StorageManager(app.config["DB_PATH"])
    return g.storage


@app.teardown_appcontext
def close_storage(exc):
    s = g.pop("storage", None)
    if s:
        s.close()


@app.route("/")
def dashboard():
    storage = get_storage()
    status_rows = storage.get_watchlist_status()
    recent_signals = storage.get_signals(limit=20)
    symbols = sorted({r["symbol"] for r in status_rows})
    return render_template("dashboard.html", status_rows=status_rows,
                           recent_signals=recent_signals, symbols=symbols)


@app.route("/ohlcv")
def ohlcv():
    storage = get_storage()
    status_rows = storage.get_watchlist_status()
    symbols = sorted({r["symbol"] for r in status_rows})
    timeframes = ["1H", "1D", "1W", "1M"]

    symbol = request.args.get("symbol", "")
    timeframe = request.args.get("timeframe", "1D")
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    page = max(1, int(request.args.get("page", 1)))

    rows = []
    total_rows = 0
    total_pages = 1

    if symbol:
        from datetime import datetime
        start_dt = datetime.fromisoformat(start) if start else None
        end_dt = datetime.fromisoformat(end) if end else None
        # get count first (fetch extra to estimate)
        all_df = storage.get_ohlcv(symbol, timeframe, start_dt=start_dt, end_dt=end_dt)
        total_rows = len(all_df)
        total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, total_pages)
        offset = (page - 1) * PAGE_SIZE
        # slice in python (data already fetched)
        page_df = all_df.iloc[offset:offset + PAGE_SIZE]
        rows = page_df.to_dict("records")

    return render_template("ohlcv.html", symbols=symbols, timeframes=timeframes,
                           symbol=symbol, timeframe=timeframe, start=start, end=end,
                           rows=rows, page=page, total_pages=total_pages, total_rows=total_rows)


@app.route("/indicators")
def indicators():
    storage = get_storage()
    status_rows = storage.get_watchlist_status()
    symbols = sorted({r["symbol"] for r in status_rows})
    timeframes = ["1H", "1D", "1W", "1M"]

    symbol = request.args.get("symbol", "")
    timeframe = request.args.get("timeframe", "1D")
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    selected_names = request.args.getlist("names")
    page = max(1, int(request.args.get("page", 1)))

    available_names = []
    rows = []
    columns = []
    total_rows = 0
    total_pages = 1

    if symbol:
        from datetime import datetime
        available_names = storage.get_all_indicator_names(symbol, timeframe)
        start_dt = datetime.fromisoformat(start) if start else None
        end_dt = datetime.fromisoformat(end) if end else None
        names_filter = selected_names if selected_names else None
        df = storage.get_indicators(symbol, timeframe, start_dt=start_dt, end_dt=end_dt, names=names_filter)
        total_rows = len(df)
        total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, total_pages)
        offset = (page - 1) * PAGE_SIZE
        page_df = df.iloc[offset:offset + PAGE_SIZE]
        columns = list(page_df.columns)
        rows = page_df.reset_index().to_dict("records") if not page_df.empty else []

    return render_template("indicators.html", symbols=symbols, timeframes=timeframes,
                           symbol=symbol, timeframe=timeframe, start=start, end=end,
                           available_names=available_names, selected_names=selected_names,
                           columns=columns, rows=rows,
                           page=page, total_pages=total_pages, total_rows=total_rows)


@app.route("/signals")
def signals_view():
    storage = get_storage()
    status_rows = storage.get_watchlist_status()
    symbols = sorted({r["symbol"] for r in status_rows})
    timeframes = ["", "1H", "1D", "1W", "1M"]
    severities = ["alert", "warning", "info"]

    symbol = request.args.get("symbol", "")
    timeframe = request.args.get("timeframe", "")
    selected_severities = request.args.getlist("severity") or severities
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    page = max(1, int(request.args.get("page", 1)))

    from datetime import datetime
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None

    all_signals = storage.get_signals(
        start_dt=start_dt, end_dt=end_dt,
        severity=selected_severities if selected_severities != severities else None,
        symbols=[symbol] if symbol else None,
        timeframe=timeframe if timeframe else None,
    )
    total_rows = len(all_signals)
    total_pages = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)
    offset = (page - 1) * PAGE_SIZE
    rows = all_signals[offset:offset + PAGE_SIZE]

    return render_template("signals.html", symbols=symbols, timeframes=timeframes,
                           severities=severities,
                           symbol=symbol, timeframe=timeframe,
                           selected_severities=selected_severities,
                           start=start, end=end,
                           rows=rows, page=page, total_pages=total_pages, total_rows=total_rows)
