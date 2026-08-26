# 🤖 ATS Form Filler v2.2 — Semi-Automated Job Application Assistant

> **⛔ CORE RULE: This tool NEVER auto-submits applications.** It fills recognized fields and strictly stops for human review and manual submission.

A production-grade Python + Playwright automation tool designed to eliminate repetitive data entry on Applicant Tracking Systems (ATS). It connects seamlessly to your existing logged-in browser session via Chrome DevTools Protocol (CDP), fills form fields using structured candidate data, and **halts for you to review and submit manually**.

---

## 🎯 Supported ATS Platforms

| Platform | URL Pattern | Architecture | Status |
|---|---|---|---|
| **Greenhouse** | `boards.greenhouse.io/*`, embedded iframes | Server-rendered & Iframe forms | ✅ Fully Supported |
| **Lever** | `jobs.lever.co/*` | Dynamic modern forms | ✅ Fully Supported |
| **Workday** | `*.myworkdayjobs.com/*`, `workday.com/*` | React SPA (`data-automation-id`) | ✅ Fully Supported |
| **SmartRecruiters** | `careers.smartrecruiters.com/*` | React SPA (`data-test-id`) | ✅ Fully Supported |

---

## 🚀 Key Features

- **⚡ Multi-ATS Platform Support**: Built-in specialized fillers for Greenhouse (including iframe support), Lever, Workday, and SmartRecruiters.
- **🛡️ Bot-Safe Human Mode (`--human-mode`)**: Types character-by-character with randomized 40–180ms keystroke delays to bypass bot detection.
- **🔄 Auto-Scroll & Resilient Retry**: Automatically scrolls fields into view before filling and retries once upon timeout.
- **📸 Intelligent Visual Capture**:
  - Full-page screenshot on completion (`--screenshot`).
  - **Instant Failure Snapshot**: Saves DOM screenshots immediately to `screenshots/failures/` whenever an ATS layout changes.
- **📁 Enterprise Batch Processing (`--batch-dir`, `--batch-delay`)**: Sequentially processes directories of candidate JSONs with configurable rate-limiting and progress bars.
- **📊 Real-World Data Normalization**:
  - Handles international phone numbers (E.164, country code extraction).
  - Decomposes complex names, stripping suffixes and honorifics.
  - Parses geographic locations into City, State, Country.
  - Cleans Unicode smart quotes, non-breaking spaces, and hidden characters.
- **🔍 ATS Form Health Check (`--check-selectors`)**: Read-only diagnostic scanner that checks DOM selector health and detects selector drift without modifying the page.
- **📈 Job Application Pipeline Tracker (`--show-tracker`)**: Job-level CSV tracking recording company, ATS platform, and success rates.
- **🌐 Standalone HTML Dashboard (`--export-dashboard`)**: Generates an interactive, searchable, self-contained HTML pipeline report.
- **📑 Session Reports (`fill_reports/`, `--show-reports`)**: Color-coded CLI review of past fill sessions.
- **🔎 Completeness Scoring (`--validate-only`)**: Audits candidate data quality, scoring completeness from 0-100% with grade rating.

---

## 📋 Prerequisites

- **Python 3.11+**
- **Google Chrome** or **Microsoft Edge** browser
- **Resume parser backend** (or local JSON files)

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

### 2. Navigate to Application

In the debug browser window, navigate to any job application page on Greenhouse, Lever, Workday, or SmartRecruiters.

### 3. Run Commands

```bash
# --- Standard Single-Candidate Fill ---
python -m src.main --data-file sample_candidate.json

# --- Human-like Typing Mode (Recommended for bot-detection avoidance) ---
python -m src.main --data-file sample_candidate.json --human-mode

# --- Fill with Post-Fill Screenshot ---
python -m src.main --data-file sample_candidate.json --screenshot

# --- Dry Run (Preview what will be filled without touching the browser) ---
python -m src.main --data-file sample_candidate.json --dry-run

# --- Data Completeness & Quality Validation ---
python -m src.main --data-file sample_candidate.json --validate-only
python -m src.main --batch-dir samples/ --validate-only

# --- Batch Processing Across Multiple Candidates ---
python -m src.main --batch-dir samples/ --batch-delay 5 --human-mode

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
├── samples/                          # Sample candidate profiles for batch testing
├── requirements.txt                  # Python dependencies
├── pyproject.toml                    # Pytest configuration
├── launch_browser.bat                # Windows Chrome launcher script
├── src/
│   ├── main.py                       # CLI orchestrator & commands
│   ├── config.py                     # Environment settings
│   ├── models.py                     # Pydantic v2 data contract
│   ├── normalizer.py                 # Phone, location, name, text sanitization
│   ├── api_client.py                 # Async backend API client
│   ├── browser.py                    # Playwright CDP session manager
│   ├── ats_router.py                 # ATS platform detection & routing
│   ├── exceptions.py                 # Custom error hierarchy (fail loudly)
│   ├── reporter.py                   # JSON session report generator
│   ├── tracker.py                    # Job-level pipeline tracker (CSV)
│   ├── exporter.py                   # Interactive HTML dashboard generator
│   ├── validator.py                  # Candidate completeness & schema auditor
│   ├── health_check.py               # Selector health & drift diagnostic
│   ├── batch.py                      # Batch runner with rate limiting
│   └── fillers/
│       ├── base.py                   # Abstract base class (retry, scroll, human type)
│       ├── greenhouse.py             # Greenhouse ATS filler (with iframe support)
│       ├── lever.py                  # Lever ATS filler
│       ├── workday.py                # Workday ATS filler
│       └── smartrecruiters.py        # SmartRecruiters ATS filler
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
    └── test_batch.py                 # Batch processing engine tests
```

---

## 🧪 Running Tests

Run the full automated test suite:

```bash
python -m pytest tests/ -v
```

---

## ⚖️ Core Philosophy

1. **Never Auto-Submit**: The script will **never** click Submit/Apply. The user maintains 100% control over the application.
2. **Fail Loudly, Never Silently**: If an ATS layout changes, specific errors and DOM failure screenshots are created rather than typing into incorrect fields.
3. **Resilient & Human-Centric**: Multi-selector fallbacks, automatic scroll-into-view, and human-like typing ensure maximum compatibility with real-world ATS pages.
