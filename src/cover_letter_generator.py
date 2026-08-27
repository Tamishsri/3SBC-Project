"""Smart Contextual Cover Letter Personalization Engine.

Extracts job title and company metadata from the active application web page
and synthesizes a tailored, professional cover letter referencing the specific
role, target company, and candidate's top technical accomplishments.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse
from playwright.async_api import Page

from src.models import CandidateData
from src.tracker import guess_company

logger = logging.getLogger(__name__)


async def extract_page_job_context(page: Page) -> dict[str, str]:
    """Extract company name and job title from active page metadata and DOM headers.

    Args:
        page: Active Playwright Page instance.

    Returns:
        Dict with keys 'company' and 'role'.
    """
    url = page.url
    guessed_company = guess_company(url)
    role = "Software Engineer"

    # 1. Try OpenGraph and meta tags
    try:
        og_site_loc = page.locator("meta[property='og:site_name'], meta[name='author']").first
        if await og_site_loc.count() > 0:
            og_site = await og_site_loc.get_attribute("content")
            if og_site and guessed_company == "Unknown":
                guessed_company = og_site.strip()
    except Exception:
        pass

    # 2. Try H1 / primary job heading
    try:
        h1_loc = page.locator("h1, [data-automation-id='jobTitle'], .job-title, .posting-headline h2").first
        if await h1_loc.count() > 0:
            h1_text = (await h1_loc.text_content() or "").strip()
            if h1_text and len(h1_text) < 100:
                clean_role = re.sub(r"^(apply for|job opening:?|position:?)\s*", "", h1_text, flags=re.I).strip()
                if clean_role:
                    role = clean_role
    except Exception:
        pass

    # 3. If role still default, inspect <title>
    if role == "Software Engineer":
        try:
            page_title = await page.title()
            if page_title:
                parts = [p.strip() for p in re.split(r"[-|–—•]", page_title) if p.strip()]
                if parts:
                    clean_title = re.sub(r"^(apply for|careers?|jobs?)\s*", "", parts[0], flags=re.I).strip()
                    if clean_title:
                        role = clean_title
                if len(parts) >= 2 and guessed_company == "Unknown":
                    guessed_company = parts[-1]
        except Exception:
            pass

    return {
        "company": guessed_company if guessed_company != "Unknown" else "your engineering team",
        "role": role,
    }


def generate_contextual_cover_letter(
    candidate: CandidateData,
    company: str = "your team",
    role: str = "Software Engineer",
) -> str:
    """Synthesize a personalized, professional cover letter.

    Args:
        candidate: Validated CandidateData instance.
        company: Target company name.
        role: Target job title.

    Returns:
        Structured cover letter string.
    """
    p = candidate.personal
    skills_list = candidate.skills[:5]
    skills_str = ", ".join(skills_list) if skills_list else "system automation, modern backend architectures, and API development"

    exp_highlight = ""
    if candidate.experience:
        recent = candidate.experience[0]
        exp_highlight = (
            f"Most recently at {recent.company} as a {recent.title}, I led initiatives focused on building "
            f"reliable, high-throughput solutions while collaborating across cross-functional teams. "
        )

    letter = (
        f"Dear {company} Hiring Team,\n\n"
        f"I am writing to express my strong enthusiasm for the {role} opportunity at {company}. "
        f"With deep expertise in {skills_str}, I am eager to bring my hands-on experience and problem-solving mindset to your mission.\n\n"
        f"{exp_highlight}"
        f"What excites me most about {company} is the opportunity to contribute to impactful systems, deliver high-quality code, "
        f"and drive technical excellence within a forward-thinking engineering culture.\n\n"
        f"Thank you for your time and consideration. I welcome the opportunity to discuss how my background aligns with your team's upcoming goals.\n\n"
        f"Sincerely,\n"
        f"{p.full_name}\n"
        f"{p.email} | {p.phone or ''}"
    )

    return letter.strip()


async def augment_candidate_cover_letter(
    candidate: CandidateData,
    page: Page,
    force: bool = False,
) -> CandidateData:
    """Populate candidate.cover_letter dynamically if not already provided or if force=True."""
    if candidate.cover_letter and not force:
        return candidate

    context = await extract_page_job_context(page)
    generated = generate_contextual_cover_letter(
        candidate=candidate,
        company=context["company"],
        role=context["role"],
    )

    updated_dict = candidate.model_dump()
    updated_dict["cover_letter"] = generated
    logger.info("[COVER LETTER] Generated contextual cover letter for '%s' at '%s'", context["role"], context["company"])
    return CandidateData.model_validate(updated_dict)
