from dataclasses import dataclass, asdict
from typing import List, Dict
import re
import json

TOOL_VOCAB = [
    "Python", "SQL", "Spark", "Airflow", "Kafka", "Docker", "Kubernetes",
    "Azure", "Databricks", "Delta Lake", "Power BI", "DAX", "FastAPI",
    "Pytest", "GitHub Actions", "CI/CD", "MLflow", "LangChain", "RAG"
]

@dataclass
class Bullet:
    text: str
    metrics: List[str]
    tools: List[str]

def extract_metrics(text: str) -> List[str]:
    patterns = [
        r"\b\d+(\.\d+)?\s?%",
        r"\$\s?\d[\d,]*(\.\d+)?",
        r"\b\d+\+?\b",
        r"\b\d+\s?(ms|s|sec|min|hours|days)\b",
        r"\bfrom\b.+\bto\b.+"
    ]
    found = []
    for p in patterns:
        found.extend(re.findall(p, text, flags=re.IGNORECASE))
    # re.findall with groups may return tuples; normalize:
    normalized = []
    for f in found:
        normalized.append("".join(f) if isinstance(f, tuple) else f)
    return list(dict.fromkeys(normalized))

def extract_tools(text: str, vocab: List[str]) -> List[str]:
    lower = text.lower()
    return [t for t in vocab if t.lower() in lower]

def parse_markdown_bullets(md_text: str) -> List[Dict]:
    bullets = []
    for line in md_text.splitlines():
        s = line.strip()
        if s.startswith("- ") or s.startswith("* "):
            txt = s[2:].strip()
            bullets.append(asdict(Bullet(
                text=txt,
                metrics=extract_metrics(txt),
                tools=extract_tools(txt, TOOL_VOCAB)
            )))
    return bullets

if __name__ == "__main__":
    sample = """
- Reduced ETL runtime from 30 min to 8 min by moving to CDC merge upserts.
- Cut cloud spend by $3,200 monthly through AKS autoscaling.
"""
    print(json.dumps(parse_markdown_bullets(sample), indent=2))
