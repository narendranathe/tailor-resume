"""
profile_extractor.py
Parses resume artifacts (markdown, LaTeX, plain blobs, LinkedIn text) into
a canonical profile JSON. PII is never stored — caller passes text at runtime.

Usage:
    python profile_extractor.py --input resume.md --format markdown
    python profile_extractor.py --input resume.tex --format latex
    python profile_extractor.py --input blob.txt --format blob
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Tool vocabulary — extend as needed
# ---------------------------------------------------------------------------
TOOL_VOCAB: List[str] = [
    "Python", "SQL", "Bash", "Java", "Scala",
    "Spark", "Kafka", "Airflow", "Dagster", "dbt",
    "Docker", "Kubernetes", "Terraform",
    "Azure", "AWS", "GCP", "Databricks", "Delta Lake", "Iceberg",
    "Microsoft Fabric", "Power BI", "DAX",
    "FastAPI", "Flask", "React", "Streamlit",
    "PostgreSQL", "MySQL", "Redis", "Elasticsearch",
    "Pytest", "GitHub Actions", "Azure DevOps", "CI/CD",
    "MLflow", "LangChain", "RAG", "Pinecone", "pgvector",
    "Prometheus", "Grafana", "Monte Carlo", "Great Expectations",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class Bullet:
    text: str
    metrics: List[str]
    tools: List[str]
    evidence_source: str = "unknown"
    confidence: str = "medium"  # high | medium | low


@dataclass
class Role:
    title: str
    company: str
    start: str
    end: str
    location: str
    bullets: List[Bullet] = field(default_factory=list)


@dataclass
class Project:
    name: str
    tech: List[str]
    bullets: List[Bullet] = field(default_factory=list)
    date: str = ""


@dataclass
class Profile:
    experience: List[Role] = field(default_factory=list)
    projects: List[Project] = field(default_factory=list)
    skills: List[str] = field(default_factory=list)
    education: List[Dict] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Metric extraction
# ---------------------------------------------------------------------------
METRIC_PATTERNS = [
    r"\b\d+(\.\d+)?\s?%",                        # percentages
    r"\$\s?\d[\d,]*(\.\d+)?[kmb]?",               # dollar amounts
    r"\b\d+[kmb]?\+?\s?(rows|users|events|tps|rps|requests)",  # volume
    r"\b\d+\s?(ms|s|sec|min|hours|days|weeks)\b", # time
    r"\bfrom\b.{3,40}\bto\b.{3,40}",              # from X to Y
    r"\b\d+x\b",                                   # multipliers
]


def extract_metrics(text: str) -> List[str]:
    found: List[str] = []
    for pattern in METRIC_PATTERNS:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        for m in matches:
            found.append("".join(m) if isinstance(m, tuple) else m)
    return list(dict.fromkeys(found))  # dedupe, preserve order


def extract_tools(text: str) -> List[str]:
    lower = text.lower()
    return [t for t in TOOL_VOCAB if t.lower() in lower]


def score_confidence(text: str) -> str:
    metrics = extract_metrics(text)
    if len(metrics) >= 2:
        return "high"
    if len(metrics) == 1:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_blob(text: str, source: str = "blob") -> Profile:
    """
    Parse free-form work experience blob.
    Detects role headers like:
        Company: Foo  /  Title: Bar  /  Dates: Jan 2022 – Present
    and bullet lines starting with - or *.
    """
    profile = Profile()
    current_role: Optional[Role] = None
    lines = text.splitlines()

    role_header_re = re.compile(
        r"(?:company|employer|org(?:anization)?)[:\s]+(.+)", re.IGNORECASE
    )
    title_re = re.compile(r"(?:title|position|role)[:\s]+(.+)", re.IGNORECASE)
    date_re = re.compile(
        r"(?:dates?|period|tenure)[:\s]+(.+?)[\s]*(?:–|-|to)[\s]*(.+)", re.IGNORECASE
    )

    for line in lines:
        s = line.strip()
        if not s:
            continue

        m = role_header_re.match(s)
        if m:
            current_role = Role(
                title="", company=m.group(1).strip(),
                start="", end="", location=""
            )
            profile.experience.append(current_role)
            continue

        m = title_re.match(s)
        if m and current_role:
            current_role.title = m.group(1).strip()
            continue

        m = date_re.match(s)
        if m and current_role:
            current_role.start = m.group(1).strip()
            current_role.end = m.group(2).strip()
            continue

        if (s.startswith("- ") or s.startswith("* ")) and current_role:
            txt = s[2:].strip()
            bullet = Bullet(
                text=txt,
                metrics=extract_metrics(txt),
                tools=extract_tools(txt),
                evidence_source=source,
                confidence=score_confidence(txt),
            )
            current_role.bullets.append(bullet)

    return profile


def parse_markdown(text: str, source: str = "markdown_resume") -> Profile:
    """Parse a markdown resume with ## headings and - bullet lists."""
    profile = Profile()
    lines = text.splitlines()
    section = ""
    current_role: Optional[Role] = None

    for line in lines:
        s = line.strip()
        if s.startswith("## "):
            section = s[3:].lower()
            continue
        if not s:
            continue

        if "experience" in section or "work" in section:
            # Detect role lines: "**Title** | Company | Date"
            role_match = re.match(
                r"\*\*(.+?)\*\*\s*[|@]\s*(.+?)\s*[|@]\s*(.+)", s
            )
            if role_match:
                current_role = Role(
                    title=role_match.group(1).strip(),
                    company=role_match.group(2).strip(),
                    start=role_match.group(3).strip(),
                    end="",
                    location="",
                )
                profile.experience.append(current_role)
                continue

            if (s.startswith("- ") or s.startswith("* ")) and current_role:
                txt = s[2:].strip()
                current_role.bullets.append(Bullet(
                    text=txt,
                    metrics=extract_metrics(txt),
                    tools=extract_tools(txt),
                    evidence_source=source,
                    confidence=score_confidence(txt),
                ))

        elif "skill" in section:
            # Flatten skill lines into list
            for skill in re.split(r"[,|•]", s):
                sk = skill.strip(" -*")
                if sk:
                    profile.skills.append(sk)

    return profile


def parse_latex(text: str, source: str = "latex_resume") -> Profile:
    """
    Parse a LaTeX resume using standard Jake/Sourabh template commands:
        \resumeSubheading{Title}{Date}{Company}{Location}
        \resumeItem{bullet text}
        \resumeProjectHeading{Name | Tech}{Date}
    """
    profile = Profile()
    current_role: Optional[Role] = None
    current_project: Optional[Project] = None

    subheading_re = re.compile(
        r"\\resumeSubheading\{(.+?)\}\{(.+?)\}\{(.+?)\}\{(.+?)\}"
    )
    item_re = re.compile(r"\\resumeItem\{(.+?)\}", re.DOTALL)
    project_re = re.compile(r"\\resumeProjectHeading\{(.+?)\}\{(.+?)\}")
    section_re = re.compile(r"\\section\{(.+?)\}")

    section = ""
    for line in text.splitlines():
        s = line.strip()

        sec_m = section_re.search(s)
        if sec_m:
            section = sec_m.group(1).lower()
            continue

        sh_m = subheading_re.search(s)
        if sh_m and ("experience" in section or "work" in section or section == ""):
            current_project = None
            current_role = Role(
                title=sh_m.group(1).strip(),
                start=sh_m.group(2).split("--")[0].strip(),
                end=sh_m.group(2).split("--")[-1].strip() if "--" in sh_m.group(2) else "",
                company=sh_m.group(3).strip(),
                location=sh_m.group(4).strip(),
            )
            profile.experience.append(current_role)
            continue

        proj_m = project_re.search(s)
        if proj_m:
            current_role = None
            raw = proj_m.group(1)
            name_tech = raw.split("$|$") if "$|$" in raw else raw.split("|")
            name = re.sub(r"\\textbf\{(.+?)\}", r"\1", name_tech[0]).strip()
            tech_str = re.sub(r"\\emph\{(.+?)\}", r"\1", name_tech[1]).strip() if len(name_tech) > 1 else ""
            current_project = Project(
                name=name,
                tech=[t.strip() for t in tech_str.split(",")],
                date=proj_m.group(2).strip(),
            )
            profile.projects.append(current_project)
            continue

        item_m = item_re.search(s)
        if item_m:
            txt = item_m.group(1).strip()
            # Remove LaTeX escapes
            txt = re.sub(r"\\[a-zA-Z]+\{(.+?)\}", r"\1", txt)
            txt = re.sub(r"\\[a-zA-Z]+", "", txt).strip()
            bullet = Bullet(
                text=txt,
                metrics=extract_metrics(txt),
                tools=extract_tools(txt),
                evidence_source=source,
                confidence=score_confidence(txt),
            )
            if current_role:
                current_role.bullets.append(bullet)
            elif current_project:
                current_project.bullets.append(bullet)

    return profile


def parse_linkedin(text: str) -> Profile:
    """
    Parse LinkedIn PDF export (pasted as plain text).
    LinkedIn exports have inconsistent formatting; this is a best-effort parser.
    """
    return parse_blob(text, source="linkedin_pdf")


# ---------------------------------------------------------------------------
# Merge profiles
# ---------------------------------------------------------------------------
def merge_profiles(*profiles: Profile) -> Profile:
    """Merge multiple parsed profiles into one canonical profile."""
    merged = Profile()
    for p in profiles:
        merged.experience.extend(p.experience)
        merged.projects.extend(p.projects)
        merged.skills.extend(p.skills)
        merged.education.extend(p.education)
        merged.certifications.extend(p.certifications)
    merged.skills = list(dict.fromkeys(merged.skills))  # dedupe
    return merged


def profile_to_dict(profile: Profile) -> dict:
    return asdict(profile)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Extract profile from resume artifact.")
    parser.add_argument("--input", required=True, help="Path to input file")
    parser.add_argument(
        "--format",
        choices=["markdown", "latex", "blob", "linkedin"],
        default="blob",
        help="Input format",
    )
    parser.add_argument("--output", default="-", help="Output JSON path (- for stdout)")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        text = f.read()

    parsers = {
        "markdown": parse_markdown,
        "latex": parse_latex,
        "blob": parse_blob,
        "linkedin": parse_linkedin,
    }
    profile = parsers[args.format](text)
    result = json.dumps(profile_to_dict(profile), indent=2)

    if args.output == "-":
        print(result)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(result)


if __name__ == "__main__":
    # Quick smoke test
    sample_blob = """
Company: Acme Corp
Title: Data Engineer
Dates: Jan 2022 – Present

- Architected governed semantic layer on data lakehouse, cutting support tickets by ~40% and query time from 12s to under 4s.
- Compressed deployment cycles from 3 months to 14 days via Azure DevOps CI/CD end-to-end ownership.
- Reengineered CDC ETL from full-table reloads to incremental merge upserts, cutting runtime from 30 min to 8 min and compute costs by ~67%.
"""
    p = parse_blob(sample_blob)
    print(json.dumps(profile_to_dict(p), indent=2))
