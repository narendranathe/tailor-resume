"""
check_deployment_readiness.py

Smoke-test critical runtime dependencies for the tailor-resume deployments.

Run as `make check-deps`, or before a deploy, or in CI. Exits non-zero if any
CRITICAL dep is missing — so a broken environment is caught before the pipeline
silently degrades to garbage PDF parsing.

Critical deps were chosen because their absence causes *silent quality
degradation* (parser falls back to a lower tier and produces wrong output
without raising). Recommended/optional deps degrade only a single feature
without affecting the rest of the pipeline.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class DepCheck:
    """Result of importing a single dependency."""

    package: str       # pip-installable name
    module: str        # import name (may differ from pip name)
    importable: bool
    severity: str      # "critical" | "recommended" | "optional"
    impact: str        # what breaks when missing
    install_hint: str  # exact command to fix


# (pip_name, import_name, severity, impact_when_missing, install_command)
_DEPS = [
    (
        "pdfminer.six",
        "pdfminer",
        "critical",
        "PDF extraction falls through to the stdlib tier, which mangles "
        "Jake-template / LaTeX-generated PDFs (pipe separators become 'j', "
        "bullet glyphs become 'ffi', section detection breaks).",
        "pip install pdfminer.six",
    ),
    (
        "pypdf",
        "pypdf",
        "critical",
        "PDF extraction skips the second tier and falls all the way to stdlib.",
        "pip install pypdf",
    ),
    (
        "python-docx",
        "docx",
        "recommended",
        ".docx upload uses the stdlib fallback extractor with limited fidelity.",
        "pip install python-docx",
    ),
    (
        "anthropic",
        "anthropic",
        "recommended",
        "Claude-vision PDF fallback disabled. PDFs that fail all parser tiers "
        "can't be retried via the vision API.",
        "pip install anthropic",
    ),
    (
        "fastapi",
        "fastapi",
        "optional",
        "Web backend (web_app) won't start. CLI and Streamlit are unaffected.",
        "pip install fastapi uvicorn python-multipart",
    ),
    (
        "streamlit",
        "streamlit",
        "optional",
        "Streamlit UI won't start. CLI and FastAPI backend are unaffected.",
        "pip install streamlit",
    ),
]


def check_all() -> List[DepCheck]:
    """Run every dep check and return the result list in declaration order."""
    results: List[DepCheck] = []
    for pip_name, import_name, severity, impact, hint in _DEPS:
        try:
            __import__(import_name)
            ok = True
        except ImportError:
            ok = False
        results.append(
            DepCheck(
                package=pip_name,
                module=import_name,
                importable=ok,
                severity=severity,
                impact=impact,
                install_hint=hint,
            )
        )
    return results


def critical_missing(checks: List[DepCheck]) -> List[DepCheck]:
    """Subset of `checks` that are missing AND tagged 'critical'."""
    return [c for c in checks if not c.importable and c.severity == "critical"]


def format_report(checks: List[DepCheck]) -> str:
    """Render the readiness report as a human-readable multi-line string."""
    lines = ["Deployment readiness check", "=" * 60]
    for c in checks:
        status = "OK" if c.importable else "MISSING"
        lines.append(f"  [{status:>7s}] {c.package:<14s}  ({c.severity})")
        if not c.importable:
            lines.append(f"            impact : {c.impact}")
            lines.append(f"            fix    : {c.install_hint}")
    lines.append("=" * 60)
    missing = critical_missing(checks)
    if missing:
        names = ", ".join(c.package for c in missing)
        lines.append(
            f"FAILED: {len(missing)} critical dep(s) missing ({names}) — "
            "deployment will silently produce broken output."
        )
    else:
        lines.append("PASS: all critical deps installed.")
    return "\n".join(lines)


def main() -> int:
    """Print the readiness report and return exit code 0 (pass) or 1 (fail)."""
    checks = check_all()
    print(format_report(checks))
    return 1 if critical_missing(checks) else 0


if __name__ == "__main__":
    sys.exit(main())
