"""
Simple placeholder renderer for LaTeX resume templates.
Keep PII runtime-injected only.
"""
from pathlib import Path

def render_template(template_path: str, output_path: str, replacements: dict) -> None:
    content = Path(template_path).read_text(encoding="utf-8")
    for k, v in replacements.items():
        content = content.replace(f"{{{{{k}}}}}", v)
    Path(output_path).write_text(content, encoding="utf-8")

if __name__ == "__main__":
    # Example usage:
    # render_template("templates/resume.tex", "out/resume.tex", {"NAME":"Jane Doe"})
    pass
