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


def generate_html_dashboard(output_path: Path | None = None) -> Path:
    """Generate a modern, standalone HTML dashboard of all job applications.

    Args:
        output_path: Target path for the HTML file (default: application_dashboard.html).

    Returns:
        Path to the generated HTML file.
    """
    output_path = output_path or Path("application_dashboard.html")
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

    table_body = "\n".join(rows_html) if rows_html else '<tr><td colspan="7" class="text-center">No applications tracked yet.</td></tr>'

    # Build platform cards HTML
    platform_cards = []
    for p_name, count in platforms.items():
        platform_cards.append(f"""
        <div class="stat-card mini">
            <div class="stat-label">{p_name}</div>
            <div class="stat-val">{count}</div>
        </div>
        """)
    platform_cards_html = "\n".join(platform_cards)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ATS Form Filler — Application Pipeline Dashboard</title>
    <style>
        :root {{
            --bg: #0f172a;
            --card-bg: #1e293b;
            --border: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #38bdf8;
            --success: #4ade80;
            --warning: #facc15;
            --danger: #f87171;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            padding: 2rem;
            line-height: 1.5;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 1.5rem;
            margin-bottom: 2rem;
        }}
        h1 {{ font-size: 1.75rem; color: var(--primary); font-weight: 700; }}
        .subtitle {{ color: var(--text-muted); font-size: 0.9rem; margin-top: 0.25rem; }}
        .badge-live {{
            background: rgba(56, 189, 248, 0.15);
            color: var(--primary);
            padding: 0.4rem 0.8rem;
            border-radius: 9999px;
            font-size: 0.8rem;
            font-weight: 600;
            border: 1px solid rgba(56, 189, 248, 0.3);
        }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1.25rem; margin-bottom: 2rem; }}
        .stat-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.25rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        }}
        .stat-card.mini {{ padding: 0.75rem 1rem; }}
        .stat-label {{ color: var(--text-muted); font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.25rem; }}
        .stat-val {{ font-size: 2rem; font-weight: 700; color: var(--text); }}
        .stat-val.primary {{ color: var(--primary); }}
        .stat-val.success {{ color: var(--success); }}
        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
        }}
        .card-header {{ font-size: 1.15rem; font-weight: 600; margin-bottom: 1rem; color: var(--text); }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
            text-align: left;
        }}
        th {{
            background: #0f172a;
            color: var(--text-muted);
            font-weight: 600;
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border);
        }}
        td {{
            padding: 0.85rem 1rem;
            border-bottom: 1px solid var(--border);
            vertical-align: middle;
        }}
        tr:hover td {{ background: rgba(255, 255, 255, 0.02); }}
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.6rem;
            border-radius: 6px;
            font-weight: 600;
            font-size: 0.8rem;
        }}
        .badge-success {{ background: rgba(74, 222, 128, 0.15); color: var(--success); border: 1px solid rgba(74, 222, 128, 0.3); }}
        .badge-warning {{ background: rgba(250, 204, 21, 0.15); color: var(--warning); border: 1px solid rgba(250, 204, 21, 0.3); }}
        .badge-danger {{ background: rgba(248, 113, 113, 0.15); color: var(--danger); border: 1px solid rgba(248, 113, 113, 0.3); }}
        .platform-pill {{
            background: #334155;
            color: #cbd5e1;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.8rem;
        }}
        .job-link {{ color: var(--primary); text-decoration: none; word-break: break-all; }}
        .job-link:hover {{ text-decoration: underline; }}
        .text-success {{ color: var(--success); font-weight: 600; }}
        .text-danger {{ color: var(--danger); font-weight: 600; }}
        .text-muted {{ color: var(--text-muted); }}
        .text-center {{ text-align: center; padding: 2rem !important; color: var(--text-muted); }}
        .search-bar {{
            width: 100%;
            padding: 0.65rem 1rem;
            background: #0f172a;
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text);
            margin-bottom: 1rem;
            font-size: 0.9rem;
        }}
        .search-bar:focus {{ outline: none; border-color: var(--primary); }}
        footer {{ text-align: center; color: var(--text-muted); font-size: 0.8rem; margin-top: 2rem; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1>ATS Form Filler — Application Pipeline</h1>
                <div class="subtitle">Semi-Automated Application Staging Dashboard & Analytics</div>
            </div>
            <div class="badge-live">Updated: {now_str}</div>
        </header>

        <div class="grid">
            <div class="stat-card">
                <div class="stat-label">Total Applications</div>
                <div class="stat-val primary">{total_apps}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Avg Fill Success Rate</div>
                <div class="stat-val success">{avg_rate:.0f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Supported ATS Platforms</div>
                <div class="stat-val">4</div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">Applications by ATS Platform</div>
            <div class="grid" style="margin-bottom: 0;">
                {platform_cards_html or '<div class="text-muted">No platforms tracked yet.</div>'}
            </div>
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
            ATS Form Filler v2.4 | Built with Playwright & Python | Core Rule: Never Auto-Submits
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
    output_path.write_text(html_content, encoding="utf-8")
    return output_path
