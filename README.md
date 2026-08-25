# 🤖 ATS Form Filler — Semi-Automated Job Application Assistant

> **⛔ This tool NEVER auto-submits applications.** It fills known fields and stops for human review.

A Python + Playwright tool that takes the grunt work out of applying to Applicant Tracking Systems (ATS). It hooks into your existing logged-in browser session, pre-fills standard application fields using parsed resume data, and **halts for you to review and submit manually**.

## 🎯 Supported ATS Platforms

| Platform | URL Pattern | Status |
|----------|------------|--------|
| **Greenhouse** | `boards.greenhouse.io/*` | ✅ Supported |
| **Lever** | `jobs.lever.co/*` | ✅ Supported |

## 🏗️ Architecture

```
main.py (CLI)
  → api_client.py (fetch candidate data from backend)
  → models.py (Pydantic validation — THE CONTRACT)
  → browser.py (CDP connection to your Chrome session)
  → ats_router.py (detect ATS platform)
  → fillers/greenhouse.py or fillers/lever.py
  → ⛔ HALT FOR HUMAN REVIEW
```

## 📋 Prerequisites

- **Python 3.11+**
- **Chrome or Edge** browser
- **Resume parser backend** running (teammate Saran's module)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API token and settings
```

### 3. Launch Browser with Debug Port

Double-click `launch_browser.bat` or run manually:

```bash
chrome --remote-debugging-port=9222 --user-data-dir="%TEMP%\chrome-debug-profile"
```

### 4. Navigate to a Job Application

In the debug browser, log in and navigate to any Greenhouse or Lever job application page.

### 5. Run the Form Filler

```bash
# Fetch candidate data from API
python -m src.main --candidate-id 123

# Or use a local JSON file (for testing)
python -m src.main --data-file sample_candidate.json

# With custom options
python -m src.main --candidate-id 123 --port 9222 --debug
```

### 6. Review & Submit Manually

The script will:
1. ✅ Fill all recognized fields (Name, Email, Phone, Resume, LinkedIn, etc.)
2. ⚠️ Log warnings for any fields it couldn't find
3. ⛔ **HALT** with a clear message — you take over from here

## 🛡️ Error Handling Philosophy

This tool **fails loudly, never silently**:

- **Field not found?** → Specific error: `"Failed to locate 'Email' field on Greenhouse form. The page layout may have changed."`
- **Invalid candidate data?** → Halts BEFORE opening the browser
- **Browser not connected?** → Step-by-step instructions to fix it
- **Unsupported ATS?** → Lists all supported platforms

No generic `try/except`. Every error handler catches specific Playwright exceptions (`TimeoutError`, `Error`).

## 📊 Data Contract (for Saran's Parser)

The form filler expects data in this structure (see `src/models.py`):

```json
{
  "personal": {
    "first_name": "Tamish",
    "last_name": "Sridatta",
    "email": "tamish@example.com",
    "phone": "+1-555-0100",
    "linkedin_url": "https://linkedin.com/in/tamish",
    "location": "Chennai, India"
  },
  "experience": [
    {
      "company": "TechCorp",
      "title": "Software Engineer",
      "start_date": "2023-01",
      "description": "Built things"
    }
  ],
  "education": [
    {
      "institution": "MIT",
      "degree": "B.S. Computer Science"
    }
  ],
  "skills": ["Python", "Playwright", "FastAPI"],
  "resume_file_path": "C:/path/to/resume.pdf"
}
```

## 🧪 Running Tests

```bash
python -m pytest tests/ -v
```

## 📂 Project Structure

```
3sbc-project/
├── README.md                   # This file
├── requirements.txt            # Python dependencies
├── pyproject.toml              # Project metadata
├── .env.example                # Environment template
├── launch_browser.bat          # Browser launcher (Windows)
├── src/
│   ├── __init__.py
│   ├── main.py                 # CLI entry point & orchestrator
│   ├── config.py               # Environment configuration
│   ├── models.py               # Pydantic data models (CONTRACT)
│   ├── api_client.py           # Backend API integration
│   ├── browser.py              # Playwright CDP connection
│   ├── ats_router.py           # ATS platform detection & routing
│   ├── exceptions.py           # Custom exception hierarchy
│   └── fillers/
│       ├── __init__.py
│       ├── base.py             # ATSFormFiller abstract base class
│       ├── greenhouse.py       # Greenhouse form filler
│       └── lever.py            # Lever form filler
└── tests/
    ├── __init__.py
    └── test_models.py          # Data model tests
```

## 🔒 The Iron Rule

```python
# This line exists NOWHERE in the codebase:
# await page.click("button[type='submit']")  # ← FORBIDDEN

# Instead, every filler ends with:
return self.halt_for_review()
# ⛔ FORM FILLING COMPLETE — HALTING FOR HUMAN REVIEW
```

## 👥 Team

- **Tamish Sridatta** — ATS Form Filler (this module)
- **Saran** — Resume Parser (data provider)

## 📜 License

MIT
