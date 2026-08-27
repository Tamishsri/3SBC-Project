"""HTML & Markdown Dashboard Exporter for the ATS Application Pipeline.

Generates a standalone, visual HTML dashboard from application_log.csv and
fill_reports/ session logs. The generated HTML file requires no external
server or internet access — it can be opened directly in any browser.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.tracker import load_tracker


def build_html_dashboard_content() -> str:
    """Build the complete HTML dashboard string in memory."""
    entries = load_tracker()

    # Load session reports for deep field failure analytics
    reports_dir = Path("fill_reports")
    failed_fields_count: dict[str, int] = {}
    filled_fields_count: dict[str, int] = {}

    if reports_dir.exists():
        for rp in reports_dir.glob("*.json"):
            try:
                data = json.loads(rp.read_text(encoding="utf-8"))
                for f in data.get("failed_fields", []):
                    failed_fields_count[f] = failed_fields_count.get(f, 0) + 1
                for f in data.get("filled_fields", []):
                    filled_fields_count[f] = filled_fields_count.get(f, 0) + 1
            except Exception:
                continue

    total_apps = len(entries)
    platforms: dict[str, int] = {}
    total_rate = 0.0

    for e in entries:
        plat = e.get("ats_platform", "Unknown")
        platforms[plat] = platforms.get(plat, 0) + 1
        try:
            total_rate += float(e.get("success_rate_pct", 0))
        except ValueError:
            pass

    avg_rate = (total_rate / total_apps) if total_apps > 0 else 0.0

    # Build rows HTML
    rows_html = []
    for e in reversed(entries):
        rate = float(e.get("success_rate_pct", 0))
        badge_class = "badge-success" if rate >= 90 else ("badge-warning" if rate >= 60 else "badge-danger")
        url = e.get("job_url", "")
        url_display = (url[:45] + "...") if len(url) > 48 else url

        rows_html.append(f"""
        <tr>
            <td>{e.get('timestamp', '')}</td>
            <td><strong>{e.get('candidate_name', '')}</strong><br><small class="text-muted">{e.get('candidate_email', '')}</small></td>
            <td><span class="platform-pill">{e.get('ats_platform', '')}</span></td>
            <td><strong>{e.get('company_guess', '')}</strong></td>
            <td><a href="{url}" target="_blank" class="job-link">{url_display}</a></td>
            <td><span class="badge {badge_class}">{rate:.0f}%</span></td>
            <td><span class="text-success">{e.get('fields_filled', 0)}</span> / <span class="text-danger">{e.get('fields_failed', 0)}</span> / <span class="text-muted">{e.get('fields_skipped', 0)}</span></td>
        </tr>
        """)

    table_body = "\n".join(rows_html) if rows_html else """
    <tr>
        <td colspan="7" class="empty-state">No job applications logged yet. Run a fill command to start tracking.</td>
    </tr>
    """

    # Top platform badges
    platform_badges = " ".join(
        f'<span class="platform-pill">{plat}: {count}</span>'
        for plat, count in sorted(platforms.items(), key=lambda x: x[1], reverse=True)
    ) or '<span class="text-muted">None</span>'

    # Top failed fields
    top_failed = sorted(failed_fields_count.items(), key=lambda x: x[1], reverse=True)[:5]
    failed_pills = " ".join(
        f'<span class="badge badge-danger">{field} ({count})</span>'
        for field, count in top_failed
    ) or '<span class="text-success">None (All fields filling reliably)</span>'

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ATS Application Pipeline Dashboard</title>
    <style>
        :root {{
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-border: #334155;
            --text-primary: #f8fafc;
            --text-muted: #94a3b8;
            --accent: #38bdf8;
            --success: #4ade80;
            --warning: #facc15;
            --danger: #f87171;
            --pill-bg: #334155;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text-primary);
            line-height: 1.5;
            padding: 2rem 1rem;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            border-bottom: 1px solid var(--surface-border);
            padding-bottom: 1.5rem;
            flex-wrap: wrap;
            gap: 1rem;
        }}
        h1 {{ font-size: 1.75rem; font-weight: 700; color: var(--text-primary); }}
        .badge-live {{
            background: rgba(56, 189, 248, 0.15);
            color: var(--accent);
            border: 1px solid rgba(56, 189, 248, 0.3);
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 600;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: var(--surface);
            border: 1px solid var(--surface-border);
            padding: 1.25rem;
            border-radius: 0.75rem;
        }}
        .stat-label {{ font-size: 0.875rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; }}
        .stat-value {{ font-size: 2rem; font-weight: 700; margin-top: 0.25rem; color: var(--text-primary); }}
        .card {{
            background: var(--surface);
            border: 1px solid var(--surface-border);
            border-radius: 0.75rem;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }}
        .card-header {{ font-size: 1.15rem; font-weight: 600; margin-bottom: 1rem; }}
        .search-bar {{
            width: 100%;
            padding: 0.75rem 1rem;
            background: var(--bg);
            border: 1px solid var(--surface-border);
            color: var(--text-primary);
            border-radius: 0.5rem;
            margin-bottom: 1rem;
            font-size: 0.95rem;
        }}
        .search-bar:focus {{ outline: none; border-color: var(--accent); }}
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.9rem;
        }}
        th, td {{
            padding: 0.85rem 1rem;
            border-bottom: 1px solid var(--surface-border);
        }}
        th {{
            color: var(--text-muted);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.75rem;
            background: rgba(15, 23, 42, 0.4);
        }}
        tr:hover {{ background: rgba(255, 255, 255, 0.02); }}
        .badge {{
            padding: 0.2rem 0.5rem;
            border-radius: 0.375rem;
            font-size: 0.75rem;
            font-weight: 700;
            display: inline-block;
        }}
        .badge-success {{ background: rgba(74, 222, 128, 0.15); color: var(--success); }}
        .badge-warning {{ background: rgba(250, 204, 21, 0.15); color: var(--warning); }}
        .badge-danger {{ background: rgba(248, 113, 113, 0.15); color: var(--danger); }}
        .platform-pill {{
            background: var(--pill-bg);
            color: var(--text-primary);
            padding: 0.25rem 0.6rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            display: inline-block;
        }}
        .job-link {{ color: var(--accent); text-decoration: none; word-break: break-all; }}
        .job-link:hover {{ text-decoration: underline; }}
        .text-success {{ color: var(--success); font-weight: 600; }}
        .text-danger {{ color: var(--danger); font-weight: 600; }}
        .text-muted {{ color: var(--text-muted); }}
        .empty-state {{ text-align: center; padding: 2rem; color: var(--text-muted); font-style: italic; }}
        footer {{
            text-align: center;
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-top: 3rem;
            border-top: 1px solid var(--surface-border);
            padding-top: 1.5rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>ATS Form Filler — Application Pipeline</h1>
                <p class="text-muted">Updated: {now_str} • Semi-Automated Applications Dashboard</p>
            </div>
            <div class="badge-live">Live Pipeline Tracker</div>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total Applications</div>
                <div class="stat-value">{total_apps}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Avg Success Rate</div>
                <div class="stat-value" style="color: {'var(--success)' if avg_rate >= 90 else ('var(--warning)' if avg_rate >= 60 else 'var(--danger)')}">{avg_rate:.1f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">ATS Platforms Used</div>
                <div class="stat-value">{len(platforms)}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Top Platforms</div>
                <div style="margin-top: 0.5rem; display: flex; flex-wrap: wrap; gap: 0.35rem;">{platform_badges}</div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">Selector Health & Failure Analytics</div>
            <p class="text-muted" style="margin-bottom: 0.75rem; font-size: 0.85rem;">Most frequent field dropouts (useful for tracking ATS DOM changes):</p>
            <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">{failed_pills}</div>
        </div>

        <div class="card">
            <div class="card-header">Job Application History</div>
            <input type="text" id="searchInput" class="search-bar" placeholder="Search by candidate, company, ATS platform, or URL..." onkeyup="filterTable()">
            <div style="overflow-x: auto;">
                <table id="appsTable">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Candidate</th>
                            <th>Platform</th>
                            <th>Company</th>
                            <th>Job URL</th>
                            <th>Success Rate</th>
                            <th>Filled / Failed / Skipped</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_body}
                    </tbody>
                </table>
            </div>
        </div>

        <footer>
            ATS Form Filler v2.6 | Built with Playwright & Python | Core Rule: Never Auto-Submits
        </footer>
    </div>

    <script>
        function filterTable() {{
            const input = document.getElementById('searchInput');
            const filter = input.value.toLowerCase();
            const table = document.getElementById('appsTable');
            const tr = table.getElementsByTagName('tr');

            for (let i = 1; i < tr.length; i++) {{
                const rowText = tr[i].textContent || tr[i].innerText;
                if (rowText.toLowerCase().indexOf(filter) > -1) {{
                    tr[i].style.display = "";
                }} else {{
                    tr[i].style.display = "none";
                }}
            }}
        }}
    </script>
</body>
</html>
"""
    return html_content


def generate_html_dashboard(output_path: Path | None = None) -> Path:
    """Generate a modern, standalone HTML dashboard of all job applications.

    Args:
        output_path: Target path for the HTML file (default: application_dashboard.html).

    Returns:
        Path to the generated HTML file.
    """
    output_path = output_path or Path("application_dashboard.html")
    html_content = build_html_dashboard_content()
    output_path.write_text(html_content, encoding="utf-8")
    return output_path
