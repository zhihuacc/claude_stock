from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

SEVERITY_ORDER = ["alert", "warning", "info"]
SEVERITY_STYLE = {
    "alert": "bold red",
    "warning": "bold yellow",
    "info": "cyan",
}


def print_signals(signals: list[dict], run_time_s: float = 0.0, db_path: str = ""):
    if not signals:
        console.print("[dim]No signals triggered.[/dim]")
        return

    console.rule(f"[bold]Stock Signal Report — {datetime.now().strftime('%Y-%m-%d')}[/bold]")

    by_severity = {s: [] for s in SEVERITY_ORDER}
    for sig in signals:
        sev = sig.get("severity", "info")
        by_severity.setdefault(sev, []).append(sig)

    for sev in SEVERITY_ORDER:
        group = by_severity.get(sev, [])
        if not group:
            continue
        style = SEVERITY_STYLE.get(sev, "")
        console.print(f"\n[{style}] {sev.upper()} ({len(group)})[/{style}]")
        t = Table(box=box.ROUNDED, show_header=True, header_style="bold")
        t.add_column("Symbol", style="bold")
        t.add_column("Signal")
        t.add_column("Timeframe")
        t.add_column("Value", justify="right")
        t.add_column("Threshold", justify="right")
        t.add_column("Datetime")
        for sig in sorted(group, key=lambda x: x["symbol"]):
            dt = sig["datetime"]
            dt_str = dt.strftime("%Y-%m-%d %H:%M") if hasattr(dt, "strftime") else str(dt)
            t.add_row(
                sig["symbol"],
                sig["signal_name"],
                sig["timeframe"],
                str(sig.get("current_value", "")),
                str(sig.get("threshold", "")),
                dt_str,
            )
        console.print(t)

    n_sym = len({s["symbol"] for s in signals})
    console.print(f"\n[dim]Summary: {len(signals)} signal(s) across {n_sym} symbol(s)"
                  f" | Run time: {run_time_s:.1f}s | DB: {db_path}[/dim]")


def print_status(rows: list[dict]):
    """Print watchlist status table."""
    t = Table(title="DB Status", box=box.ROUNDED, show_header=True, header_style="bold")
    for col in ["Symbol", "Timeframe", "Last Bar", "Row Count", "Last Signal"]:
        t.add_column(col)
    for row in rows:
        t.add_row(
            row.get("symbol", ""),
            row.get("timeframe", ""),
            str(row.get("last_datetime", "—")),
            str(row.get("row_count", 0)),
            row.get("last_signal", "—"),
        )
    console.print(t)
