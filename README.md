# 🤖 ATS Form Filler v2.7 — Enterprise Semi-Automated Job Application Assistant

> **⛔ CORE RULE: This tool NEVER auto-submits applications.** It fills recognized fields, auto-advances wizard steps if requested, and strictly halts for human review before final submission.

A production-grade Python + Playwright automation suite designed to eliminate repetitive data entry on Applicant Tracking Systems (ATS) and web application portals. It connects seamlessly to your existing logged-in browser session via Chrome DevTools Protocol (CDP), fills form fields using structured candidate data, and **halts for you to review and submit manually**.

---

## 🎯 Supported ATS Platforms & Web Forms

| Platform | URL Pattern / Matcher | Architecture | Status |
|---|---|---|---|
| **Greenhouse** | `boards.greenhouse.io/*`, embedded iframes | Server-rendered & Iframe forms | ✅ Fully Supported |
| **Lever** | `jobs.lever.co/*` | Dynamic modern forms | ✅ Fully Supported |
| **Workday** | `*.myworkdayjobs.com/*`, `workday.com/*` | React SPA (`data-automation-id`) | ✅ Fully Supported |
| **SmartRecruiters** | `careers.smartrecruiters.com/*` | React SPA (`data-test-id`) | ✅ Fully Supported |
| **Generic Web Form** | Ashby, BambooHR, Jobvite, Taleo, Rippling, Custom Portals | HTML5 Semantic & Heuristic Matching (`--allow-generic`) | ✅ Fully Supported |

---

## 🚀 Key Features

- **⚡ Multi-ATS & Generic Adaptive Engine (`--allow-generic`)**: Specialized fillers for Greenhouse (with iframe support), Lever, Workday, SmartRecruiters, PLUS an adaptive heuristic engine that handles arbitrary career pages worldwide.
- **❓ Interactive Field Prompter & Learner (`--interactive`)**: Prompts in the terminal when unmapped company questions are encountered, fills them immediately, and persists answers into candidate profiles/presets for future applications.
- **📥 Drop-Folder Inbox Watcher Daemon (`--watch-dir inbox/`)**: Background file watcher where dropping a resume (`.pdf`, `.txt`, `.json`) into `inbox/` automatically parses it and auto-fills your active Chrome tab.
- **🤝 Team Integration Mock API Gateway (`scripts/mock_team_backend.py`)**: Ready-to-use mock hub matching team contracts for **Saran** (Parser), **Rohit** (Scraper), and **Sushrith** (Backend API).
- **🖱️ One-Click Desktop Launchers**: Windows batch scripts (`launch_dashboard.bat`, `launch_inbox_watcher.bat`, `launch_team_hub.bat`, `run_stress_benchmark.bat`) for instant 1-click startup.
- **🛡️ Live CAPTCHA & Bot Challenge Interceptor (`--detect-captcha`)**: Detects Cloudflare Turnstile, Google reCAPTCHA, and hCaptcha, pausing with an audible alert for human resolution and auto-resuming once solved.
- **✍️ Contextual Cover Letter Synthesis (`--generate-cover-letter`)**: Scrapes target company and role context from page metadata to automatically craft a tailored, high-impact cover letter.
- **🔄 Fault-Tolerant Batch Recovery (`--resume-batch`)**: Checkpoints batch progress atomically to `.ats_batch_recovery.json` so interrupted runs resume seamlessly from the point of failure.
- **🔔 Real-Time Webhook & Slack Alerts (`--webhook-url`)**: Non-blocking asynchronous notifications to Slack incoming webhooks, Discord, Zapier, or custom HTTP endpoints upon application staging.
- **🎛️ User Preference Presets (`--save-preset`, `--use-preset`)**: Save and reuse standard Work Authorization, EEOC Demographics, custom answers, and cover letter templates.
- **📄 Offline Local Resume Fallback Parser (`--parse-resume`)**: Built-in PDF/Text parser with regex & heuristics as a high-availability offline fallback.
- **📈 Interactive Live Dashboard Server (`--serve-dashboard`)**: Embedded web server (`http://127.0.0.1:8080`) providing live application analytics with dynamic background auto-polling.
- **🛂 Work Authorization & EEOC Compliance**: Automatically fills standard legal work authorization, visa sponsorship, gender, race/ethnicity, veteran, and disability dropdowns/radios.
- **🔄 Multi-Page Step-Through Wizard (`--multi-page`)**: Automatically advances through multi-step applications (Workday/SmartRecruiters) and strictly halts only when the final Submit/Apply review screen is reached.
- **🤝 Parser Contract Verifier (`--verify-contract`)**: Diagnostic tool for teammate Saran's resume parser to validate JSON schemas, detect field aliases, and compute compatibility scores.
- **🛡️ Bot-Safe Human Mode (`--human-mode`)**: Types character-by-character with randomized 40–180ms keystroke delays to bypass bot detection.
- **🔄 Auto-Scroll & Resilient Retry**: Automatically scrolls fields into view before filling and retries once upon timeout.
- **📸 Visual Error Snapshots**: Saves DOM screenshots immediately to `screenshots/failures/` whenever an ATS layout changes.
- **📁 Enterprise Batch & Worker Pool (`--batch-dir`, `--concurrency`)**: Asynchronous worker pool with backpressure control and isolated browser tabs for high-throughput multi-user execution.
- **📊 Real-World Data Normalization**: Normalizes international phone numbers (E.164), parses locations into city/state/country, strips honorifics/suffixes, and sanitizes Unicode.
- **🔍 ATS Form Health Check (`--check-selectors`)**: Read-only diagnostic scanner that checks DOM selector health and detects selector drift without modifying the page.
- **📈 Job Application Pipeline Tracker (`--show-tracker`)**: Process-safe CSV pipeline tracking recording company, ATS platform, and success rates.
- **🌐 Standalone HTML Dashboard (`--export-dashboard`)**: Generates an interactive, searchable, self-contained HTML pipeline report.

---

## 📋 Prerequisites

- **Python 3.11+**
- **Google Chrome** or **Microsoft Edge** browser
- **Resume parser backend** (or local JSON / PDF / TXT files)

---

## 📦 Installation

```bash
# 1. Clone repository
git clone https://github.com/Tamishsri/3SBC-Project.git
cd 3sbc-project

# 2. Install dependencies
python -m pip install -r requirements.txt

# 3. Install Playwright browser binaries
python -m playwright install chromium
```

---

## 🛠️ Usage Guide

### 1. Launch Browser with Debug Port

Launch Chrome with remote debugging enabled:

```bash
# On Windows (using helper script):
launch_browser.bat

# Or manually:
chrome --remote-debugging-port=9222 --user-data-dir="%TEMP%\chrome-debug-profile"
```

### 2. Quick Desktop Launchers (Windows)

- **`launch_dashboard.bat`**: Open live web dashboard in default browser at `http://127.0.0.1:8080`.
- **`launch_inbox_watcher.bat`**: Start folder daemon to auto-fill any resume dropped into `inbox/`.
- **`launch_team_hub.bat`**: Launch the mock team backend hub for Saran, Rohit, and Sushrith.
- **`run_stress_benchmark.bat`**: Run the ultra-heavy 7-vector stress test suite.

### 3. CLI Commands

```bash
# --- Standard Single-Candidate Fill ---
python -m src.main --data-file sample_resume.json

# --- Interactive Prompter & Learning Mode (Prompts for unmapped questions & saves answers) ---
python -m src.main --data-file sample_resume.json --interactive

# --- Drop-Folder Inbox Watcher Daemon (Auto-fills resumes dropped into folder) ---
python -m src.main --watch-dir inbox

# --- Human-like Typing Mode (Recommended for bot-detection avoidance) ---
python -m src.main --data-file sample_resume.json --human-mode

# --- Generic Adaptive Fallback for Unlisted ATS Portals (Ashby, BambooHR, etc.) ---
python -m src.main --data-file sample_resume.json --allow-generic

# --- Live Bot Challenge & CAPTCHA Interceptor ---
python -m src.main --data-file sample_resume.json --detect-captcha

# --- Contextual Cover Letter Synthesis from Live Page ---
python -m src.main --data-file sample_resume.json --generate-cover-letter

# --- Multi-Page Wizard Mode (Auto-advance steps on Workday/SmartRecruiters) ---
python -m src.main --data-file sample_resume.json --multi-page

# --- Real-Time Slack / Discord / Webhook Alerts ---
python -m src.main --data-file sample_resume.json --webhook-url https://hooks.slack.com/services/...

# --- Save and Use Preference Presets ---
python -m src.main --save-preset default_us --data-file sample_resume.json
python -m src.main --list-presets
python -m src.main --data-file minimal_candidate.json --use-preset default_us

# --- Extract Candidate Data Directly from Raw Resume (PDF / TXT) ---
python -m src.main --parse-resume sample_resume.txt
python -m src.main --verify-contract sample_resume.json

# --- Start Interactive Live Dashboard Web Server ---
python -m src.main --serve-dashboard --dashboard-port 8080

# --- Verify Parser Contract (For Teammate Saran) ---
python -m src.main --verify-contract sample_resume.json

# --- Data Completeness & Quality Validation ---
python -m src.main --data-file sample_resume.json --validate-only
python -m src.main --batch-dir samples/ --validate-only

# --- High-Throughput Batch Processing with Parallel Workers ---
python -m src.main --batch-dir samples/ --concurrency 3 --user-id recruiter_1 --multi-page

# --- Resume Interrupted Batch Processing ---
python -m src.main --batch-dir samples/ --resume-batch

# --- ATS Form Health Check (Selector Diagnostic) ---
python -m src.main --check-selectors

# --- View Open Browser Tabs ---
python -m src.main --list-tabs

# --- View Past Session Reports & Tracker ---
python -m src.main --show-reports
python -m src.main --show-tracker

# --- Export Visual Interactive HTML Dashboard ---
python -m src.main --export-dashboard
```

---

## 📂 Project Architecture

```
3sbc-project/
├── sample_candidate.json             # Reference candidate JSON
├── sample_resume.txt                 # Reference raw resume document
├── sample_resume.json                # Parsed reference candidate JSON
├── samples/                          # Sample candidate profiles for batch testing
├── presets/                          # User preference presets
├── requirements.txt                  # Python dependencies
├── pyproject.toml                    # Pytest configuration
├── launch_browser.bat                # Windows Chrome launcher script
├── launch_dashboard.bat              # One-click live dashboard launcher
├── launch_inbox_watcher.bat          # One-click drop-folder watcher launcher
├── launch_team_hub.bat               # One-click team mock hub launcher
├── run_stress_benchmark.bat          # One-click ultra-heavy benchmark launcher
├── scripts/
│   ├── benchmark_stress.py           # Enterprise throughput & stress benchmark
│   ├── ultra_heavy_stress.py         # 7-vector ultra-heavy stress test suite
│   ├── mock_team_backend.py          # Team integration mock hub (Saran, Rohit, Sushrith)
│   └── generate_samples.py           # International candidate sample generator
├── src/
│   ├── main.py                       # CLI orchestrator & commands
│   ├── config.py                     # Environment settings
│   ├── models.py                     # Pydantic v2 data contract
│   ├── normalizer.py                 # Phone, location, name, text sanitization
│   ├── notifier.py                   # Real-time Webhook, Slack & Discord alerts
│   ├── presets.py                    # User preference presets manager
│   ├── resume_fallback.py            # Local PDF/TXT resume fallback parser
│   ├── interactive_prompter.py       # Terminal question prompter & learning engine
│   ├── watcher.py                    # Drop-folder inbox watcher daemon
│   ├── server.py                     # Embedded live dashboard HTTP server
│   ├── captcha_detector.py           # Live Turnstile / reCAPTCHA / bot challenge detector
│   ├── cover_letter_generator.py     # Contextual cover letter synthesis engine
│   ├── recovery.py                   # Batch session recovery & state checkpointer
│   ├── api_client.py                 # Async backend API client
│   ├── browser.py                    # Playwright CDP session manager
│   ├── ats_router.py                 # ATS platform detection & routing
│   ├── exceptions.py                 # Custom error hierarchy (fail loudly)
│   ├── file_lock.py                  # Process-safe cross-platform atomic locking
│   ├── reporter.py                   # JSON session report generator
│   ├── tracker.py                    # Job-level pipeline tracker (CSV)
│   ├── exporter.py                   # Interactive HTML dashboard generator
│   ├── validator.py                  # Candidate completeness & schema auditor
│   ├── contract_verifier.py          # Saran's parser integration contract verifier
│   ├── health_check.py               # Selector health & drift diagnostic
│   ├── batch.py                      # Batch runner with rate limiting
│   ├── worker_pool.py                # Parallel worker pool with concurrency control
│   └── fillers/
│       ├── base.py                   # Abstract base class (retry, scroll, human type, compliance, Q&A, re-injection)
│       ├── greenhouse.py             # Greenhouse ATS filler (with iframe support)
│       ├── lever.py                  # Lever ATS filler
│       ├── workday.py                # Workday ATS filler
│       ├── smartrecruiters.py        # SmartRecruiters ATS filler
│       └── generic.py                # Adaptive generic web form filler
└── tests/
    ├── test_models.py                # Pydantic model validation tests
    ├── test_normalizer.py            # Phone, location, unicode tests
    ├── test_fillers.py               # ATS detection & selector structure tests
    ├── test_api_client.py            # API client mocking tests
    ├── test_integration_fillers.py   # Live Playwright DOM fill tests
    ├── test_workday_and_reporter.py  # Workday & JSON reporter tests
    ├── test_smartrecruiters_and_features.py # SmartRecruiters & human typing tests
    ├── test_validator_and_features.py # Validator, health check & dashboard tests
    ├── test_tracker.py               # Pipeline CSV tracker tests
    ├── test_batch.py                 # Batch processing engine tests
    ├── test_concurrency.py           # Multi-threaded file lock & worker pool tests
    ├── test_fuzz_and_edge_cases.py   # Adversarial inputs & extreme sizes tests
    ├── test_heavy_load_concurrency.py # 50-thread high-contention & 100-burst tests
    ├── test_compliance_and_custom_qa.py # Work Auth, EEOC & Custom Q&A tests
    ├── test_multi_page_wizard.py     # Multi-page wizard & submit safety tests
    ├── test_contract_verifier.py     # Resume parser contract verifier tests
    ├── test_notifier.py              # Webhook & Slack alerts tests
    ├── test_presets.py               # User preference presets tests
    ├── test_resume_fallback.py       # Local PDF/TXT parser fallback tests
    ├── test_server.py                # Live dashboard HTTP server tests
    ├── test_generic_filler.py        # Adaptive generic web form filler tests
    ├── test_captcha_detector.py      # Turnstile / reCAPTCHA detector tests
    ├── test_cover_letter_generator.py # Contextual cover letter synthesis tests
    ├── test_recovery.py              # Batch checkpointing & recovery tests
    ├── test_interactive_prompter.py  # Interactive question prompter & learning tests
    ├── test_watcher.py               # Drop-folder inbox watcher daemon tests
    └── test_team_mock_backend.py     # Team integration mock hub tests
```

---

## 🧪 Running Tests & Benchmarks

```bash
# Run full automated test suite (155 tests across 26 test modules - 100% Passing):
python -m pytest tests/ -v

# Run ultra-heavy 7-vector stress & endurance benchmark:
python scripts/ultra_heavy_stress.py
```

---

## ⚖️ Core Philosophy

1. **Never Auto-Submit**: The script will **never** click Submit/Apply. The user maintains 100% control over the application.
2. **Fail Loudly, Never Silently**: If an ATS layout changes, specific errors and DOM failure screenshots are created rather than typing into incorrect fields.
3. **Resilient & Human-Centric**: Multi-selector fallbacks, automatic scroll-into-view, compliance automation, interactive question learning, and human-like typing ensure maximum compatibility with real-world ATS pages.

