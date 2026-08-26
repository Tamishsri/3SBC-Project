# 🤖 ATS Form Filler v2.4 — Semi-Automated Job Application Assistant

> **⛔ CORE RULE: This tool NEVER auto-submits applications.** It fills recognized fields, auto-advances wizard steps if requested, and strictly halts for human review before final submission.

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
- **🛂 Work Authorization & EEOC Compliance**: Automatically fills standard legal work authorization, visa sponsorship, gender, race/ethnicity, veteran, and disability dropdowns/radios.
- **❓ Dynamic Custom Question Matcher**: Intelligently matches company-specific questions (notice period, expected salary, relocation, custom answers map) using fuzzy label heuristics.
- **🔄 Multi-Page Step-Through Wizard (`--multi-page`)**: Automatically advances through multi-step applications (Workday/SmartRecruiters) and strictly halts only when the final Submit/Apply review screen is reached.
- **🤝 Parser Contract Verifier (`--verify-contract`)**: Diagnostic tool for teammate Saran's resume parser to validate JSON schemas, detect field-name aliases (`fname` -> `first_name`), and compute compatibility scores.
- **🛡️ Bot-Safe Human Mode (`--human-mode`)**: Types character-by-character with randomized 40–180ms keystroke delays to bypass bot detection.
- **🔄 Auto-Scroll & Resilient Retry**: Automatically scrolls fields into view before filling and retries once upon timeout.
- **📸 Intelligent Visual Capture**:
  - Full-page screenshot on completion (`--screenshot`).
  - **Instant Failure Snapshot**: Saves DOM screenshots immediately to `screenshots/failures/` whenever an ATS layout changes.
- **📁 Enterprise Batch & Worker Pool (`--batch-dir`, `--concurrency`)**: Asynchronous worker pool with backpressure control for high-throughput multi-user execution.
- **📊 Real-World Data Normalization**: Normalizes international phone numbers (E.164), parses locations into city/state/country, strips honorifics/suffixes, and sanitizes Unicode.
- **🔍 ATS Form Health Check (`--check-selectors`)**: Read-only diagnostic scanner that checks DOM selector health and detects selector drift without modifying the page.
- **📈 Job Application Pipeline Tracker (`--show-tracker`)**: Process-safe CSV pipeline tracking recording company, ATS platform, and success rates.
- **🌐 Standalone HTML Dashboard (`--export-dashboard`)**: Generates an interactive, searchable, self-contained HTML pipeline report.
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

# --- Multi-Page Wizard Mode (Auto-advance steps on Workday/SmartRecruiters) ---
python -m src.main --data-file sample_candidate.json --multi-page

# --- Verify Parser Contract (For Teammate Saran) ---
python -m src.main --verify-contract sample_candidate.json

# --- Data Completeness & Quality Validation ---
python -m src.main --data-file sample_candidate.json --validate-only
python -m src.main --batch-dir samples/ --validate-only

# --- High-Throughput Batch Processing with Parallel Workers ---
python -m src.main --batch-dir samples/ --concurrency 3 --user-id recruiter_1

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
├── scripts/
│   ├── benchmark_stress.py           # Enterprise throughput & stress benchmark
│   └── generate_samples.py           # International candidate sample generator
├── src/
│   ├── main.py                       # CLI orchestrator & commands
│   ├── config.py                     # Environment settings
│   ├── models.py                     # Pydantic v2 data contract
│   ├── normalizer.py                 # Phone, location, name, text sanitization
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
│       ├── base.py                   # Abstract base class (retry, scroll, human type, compliance, Q&A)
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
    ├── test_batch.py                 # Batch processing engine tests
    ├── test_concurrency.py           # Multi-threaded file lock & worker pool tests
    ├── test_fuzz_and_edge_cases.py   # Adversarial inputs & extreme sizes tests
    ├── test_heavy_load_concurrency.py # 50-thread high-contention & 100-burst tests
    ├── test_compliance_and_custom_qa.py # Work Auth, EEOC & Custom Q&A tests
    ├── test_multi_page_wizard.py     # Multi-page wizard & submit safety tests
    └── test_contract_verifier.py     # Resume parser contract verifier tests
```

---

## 🧪 Running Tests

```bash
# Run full automated test suite (16 test modules):
python -m pytest tests/ -v

# Run enterprise performance benchmark:
python scripts/benchmark_stress.py
```

---

## ⚖️ Core Philosophy

1. **Never Auto-Submit**: The script will **never** click Submit/Apply. The user maintains 100% control over the application.
2. **Fail Loudly, Never Silently**: If an ATS layout changes, specific errors and DOM failure screenshots are created rather than typing into incorrect fields.
3. **Resilient & Human-Centric**: Multi-selector fallbacks, automatic scroll-into-view, compliance automation, and human-like typing ensure maximum compatibility with real-world ATS pages.
