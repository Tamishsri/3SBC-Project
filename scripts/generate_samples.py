"""Sample candidate generator for testing large batch processing and edge cases."""

import json
from pathlib import Path

SAMPLES = [
    {
        "filename": "candidate_alex_chen.json",
        "data": {
            "personal": {
                "first_name": "Alex",
                "last_name": "Chen",
                "email": "alex.chen.dev@example.com",
                "phone": "+1 (415) 555-0199",
                "linkedin_url": "https://linkedin.com/in/alexchen-dev",
                "github_url": "https://github.com/alexchen",
                "location": "San Francisco, CA, USA",
                "website": "https://alexchen.io"
            },
            "experience": [
                {
                    "company": "Stripe",
                    "title": "Senior Backend Engineer",
                    "start_date": "2022-03",
                    "description": "Architected distributed payment processing pipelines in Go and Python."
                },
                {
                    "company": "Twilio",
                    "title": "Software Engineer",
                    "start_date": "2019-06",
                    "end_date": "2022-02",
                    "description": "Built high-throughput SMS routing services handling 100M+ messages daily."
                }
            ],
            "education": [
                {
                    "institution": "University of California, Berkeley",
                    "degree": "B.S. in Computer Science",
                    "end_date": "2019"
                }
            ],
            "skills": ["Python", "Go", "Distributed Systems", "PostgreSQL", "Kafka", "Docker", "Kubernetes", "AWS"],
            "certifications": ["AWS Certified Solutions Architect - Professional"],
            "cover_letter": "I am eager to contribute my backend systems expertise to your engineering team."
        }
    },
    {
        "filename": "candidate_elena_rostova.json",
        "data": {
            "personal": {
                "first_name": "Elena",
                "last_name": "Rostova",
                "email": "elena.rostova@example.de",
                "phone": "+49 30 901820",
                "linkedin_url": "https://linkedin.com/in/elenarostova-ml",
                "github_url": "https://github.com/erostova",
                "location": "Berlin, Germany",
                "website": "https://rostova.ai"
            },
            "experience": [
                {
                    "company": "Delivery Hero",
                    "title": "Machine Learning Engineer",
                    "start_date": "2021-09",
                    "description": "Deployed real-time ETA prediction models reducing customer wait times by 14%."
                }
            ],
            "education": [
                {
                    "institution": "Technical University of Munich (TUM)",
                    "degree": "M.Sc. in Data Engineering and Analytics",
                    "end_date": "2021"
                }
            ],
            "skills": ["Python", "PyTorch", "MLOps", "FastAPI", "TensorFlow", "Scikit-Learn", "SQL"],
            "certifications": ["Google Cloud Professional Data Engineer"],
            "cover_letter": "My background in machine learning and scalable model serving directly aligns with your requirements."
        }
    },
    {
        "filename": "candidate_rajesh_kumar.json",
        "data": {
            "personal": {
                "first_name": "Rajesh",
                "last_name": "Kumar",
                "email": "rajesh.kumar@example.in",
                "phone": "+91-9876543210",
                "linkedin_url": "https://linkedin.com/in/rajeshkumar-qa",
                "github_url": "https://github.com/rajeshkumar",
                "location": "Bengaluru, Karnataka, India",
                "website": "https://rajeshk.tech"
            },
            "experience": [
                {
                    "company": "Flipkart",
                    "title": "Lead SDET",
                    "start_date": "2020-01",
                    "description": "Led automation framework development using Playwright and Python."
                }
            ],
            "education": [
                {
                    "institution": "National Institute of Technology Karnataka",
                    "degree": "B.Tech in Information Technology",
                    "end_date": "2019"
                }
            ],
            "skills": ["Playwright", "Selenium", "Python", "pytest", "CI/CD", "GitHub Actions", "Docker", "API Testing"],
            "certifications": ["ISTQB Advanced Test Automation Engineer"],
            "cover_letter": "I bring 5+ years of automated testing and browser automation leadership."
        }
    }
]


def generate_samples(target_dir: Path | None = None) -> list[Path]:
    """Generate sample candidate JSON files in target directory."""
    target_dir = target_dir or Path("samples")
    target_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    for item in SAMPLES:
        file_path = target_dir / item["filename"]
        file_path.write_text(json.dumps(item["data"], indent=2), encoding="utf-8")
        generated.append(file_path)

    return generated


if __name__ == "__main__":
    files = generate_samples()
    print(f"Generated {len(files)} sample candidate files in samples/")
