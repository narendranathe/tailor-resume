"""
tailor_resume.cli — entry point for the `tailor-resume` CLI command.

Delegates to the bundled cli.py script after adding the scripts directory to sys.path.
"""
from __future__ import annotations

import sys
import os


_BUNDLED_TEMPLATE = os.path.join(os.path.dirname(__file__), "_templates", "resume_template.tex")


def main() -> None:
    _scripts = os.path.join(os.path.dirname(__file__), "_scripts")
    if _scripts not in sys.path:
        sys.path.insert(0, _scripts)

    # Inject bundled template if caller did not specify one explicitly.
    if "--template" not in sys.argv and os.path.exists(_BUNDLED_TEMPLATE):
        sys.argv.extend(["--template", _BUNDLED_TEMPLATE])

    from cli import main as _main  # type: ignore[import]
    _main()


if __name__ == "__main__":
    main()
