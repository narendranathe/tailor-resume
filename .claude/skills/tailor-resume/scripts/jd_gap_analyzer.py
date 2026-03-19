from collections import Counter
import re
from typing import List, Tuple

STOPWORDS = {
    "the","and","for","with","from","that","this","into","your","you","our",
    "are","have","has","was","were","will","can","not","using","use","job","role"
}

def tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\-/+.]*", text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 2]

def top_missing_signals(jd_text: str, resume_text: str, top_n: int = 5) -> List[Tuple[str, int]]:
    jd_counts = Counter(tokenize(jd_text))
    resume_counts = Counter(tokenize(resume_text))
    missing = []
    for term, freq in jd_counts.items():
        if freq >= 2 and resume_counts.get(term, 0) == 0:
            missing.append((term, freq))
    missing.sort(key=lambda x: x[1], reverse=True)
    return missing[:top_n]

if __name__ == "__main__":
    jd = "Need data quality, orchestration, airflow, ci/cd, testing, reliability, data quality."
    rs = "Built airflow pipelines and dashboards."
    print(top_missing_signals(jd, rs, top_n=5))
