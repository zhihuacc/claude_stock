import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader


def generate_report(signals: list[dict], config: dict, run_time_s: float = 0.0) -> str:
    """Generate HTML report, write to output_dir, return file path."""
    cfg = config.get("output", {}).get("html_report", {})
    output_dir = cfg.get("output_dir", "reports/output/")
    os.makedirs(output_dir, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = cfg.get("filename_template", "report_{date}.html").format(date=date_str)
    output_path = os.path.join(output_dir, filename)

    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(template_dir), autoescape=True)
    tmpl = env.get_template("report.html.j2")

    by_severity = {"alert": [], "warning": [], "info": []}
    for sig in signals:
        sev = sig.get("severity", "info")
        by_severity.setdefault(sev, []).append(sig)

    html = tmpl.render(
        date=date_str,
        signals=signals,
        by_severity=by_severity,
        run_time_s=run_time_s,
        total=len(signals),
        n_symbols=len({s["symbol"] for s in signals}),
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    if cfg.get("auto_open", False):
        import webbrowser
        webbrowser.open(f"file://{os.path.abspath(output_path)}")

    return output_path
