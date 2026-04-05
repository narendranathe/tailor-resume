"""
sync_global.py
Sync skill scripts + docs from the work dir to ~/.claude/skills/tailor-resume/

Run after any change to scripts/ or documentation files:
    python scripts/sync_global.py

Or via Makefile:
    make sync-global
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

WORK_DIR = Path(__file__).parent.parent
SKILL_DIR = WORK_DIR / ".claude" / "skills" / "tailor-resume"
GLOBAL_DIR = Path.home() / ".claude" / "skills" / "tailor-resume"

DOCS = ["SKILL.md", "REFERENCE.md", "EXAMPLES.md", "CLAUDE.md"]


def sync() -> None:
    if not SKILL_DIR.exists():
        print(f"[ERROR] Skill dir not found: {SKILL_DIR}", file=sys.stderr)
        sys.exit(1)

    GLOBAL_DIR.mkdir(parents=True, exist_ok=True)

    # Sync scripts/
    src_scripts = SKILL_DIR / "scripts"
    dst_scripts = GLOBAL_DIR / "scripts"
    shutil.copytree(src_scripts, dst_scripts, dirs_exist_ok=True)
    print(f"[OK] scripts/  -> {dst_scripts}")

    # Sync templates/
    src_templates = SKILL_DIR / "templates"
    if src_templates.exists():
        dst_templates = GLOBAL_DIR / "templates"
        shutil.copytree(src_templates, dst_templates, dirs_exist_ok=True)
        print(f"[OK] templates/ -> {dst_templates}")

    # Sync docs
    for doc in DOCS:
        src = SKILL_DIR / doc
        if src.exists():
            shutil.copy2(src, GLOBAL_DIR / doc)
            print(f"[OK] {doc}")
        else:
            print(f"[SKIP] {doc} not found in work dir")

    print(f"\n[DONE] Synced to {GLOBAL_DIR}")


if __name__ == "__main__":
    sync()
