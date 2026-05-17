"""Tests for scripts/check_deployment_readiness.py."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from check_deployment_readiness import (  # noqa: E402
    DepCheck,
    check_all,
    critical_missing,
    format_report,
    main,
)


# ---------------------------------------------------------------------------
# check_all
# ---------------------------------------------------------------------------

class TestCheckAll:
    def test_returns_list_of_dep_checks(self):
        result = check_all()
        assert isinstance(result, list)
        assert all(isinstance(c, DepCheck) for c in result)

    def test_includes_critical_pdf_deps(self):
        result = check_all()
        package_names = {c.package for c in result}
        assert "pdfminer.six" in package_names
        assert "pypdf" in package_names

    def test_every_severity_is_known(self):
        valid = {"critical", "recommended", "optional"}
        for c in check_all():
            assert c.severity in valid, f"{c.package} has unknown severity {c.severity!r}"

    def test_every_critical_dep_has_install_hint(self):
        for c in check_all():
            if c.severity == "critical":
                assert c.install_hint.startswith("pip install"), (
                    f"{c.package} install_hint should be a pip command, got {c.install_hint!r}"
                )

    def test_every_dep_has_non_empty_impact(self):
        for c in check_all():
            assert c.impact and len(c.impact) > 20, (
                f"{c.package} impact should be a descriptive sentence"
            )

    def test_results_are_in_stable_order(self):
        """Two consecutive calls return the same package order — important for deterministic CI output."""
        first = [c.package for c in check_all()]
        second = [c.package for c in check_all()]
        assert first == second


# ---------------------------------------------------------------------------
# critical_missing
# ---------------------------------------------------------------------------

class TestCriticalMissing:
    def test_filters_to_missing_critical_only(self):
        checks = [
            DepCheck("a", "a", False, "critical", "impact a", "pip install a"),
            DepCheck("b", "b", True, "critical", "impact b", "pip install b"),
            DepCheck("c", "c", False, "recommended", "impact c", "pip install c"),
            DepCheck("d", "d", False, "optional", "impact d", "pip install d"),
        ]
        missing = critical_missing(checks)
        assert len(missing) == 1
        assert missing[0].package == "a"

    def test_empty_when_all_critical_installed(self):
        checks = [
            DepCheck("a", "a", True, "critical", "impact a", "pip install a"),
            DepCheck("b", "b", False, "recommended", "impact b", "pip install b"),
        ]
        assert critical_missing(checks) == []


# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_all_ok_report_says_pass(self):
        checks = [
            DepCheck("a", "a", True, "critical", "impact a", "pip install a"),
            DepCheck("b", "b", True, "optional", "impact b", "pip install b"),
        ]
        report = format_report(checks)
        assert "PASS" in report
        assert "FAILED" not in report

    def test_missing_critical_report_says_failed(self):
        checks = [
            DepCheck("a", "a", False, "critical", "impact a", "pip install a"),
            DepCheck("b", "b", True, "recommended", "impact b", "pip install b"),
        ]
        report = format_report(checks)
        assert "FAILED" in report
        assert "PASS" not in report
        assert "(a)" in report  # names listed in failure summary

    def test_missing_critical_includes_impact_and_fix(self):
        checks = [
            DepCheck("foo", "foo", False, "critical",
                     "foo breaks bar baz qux", "pip install foo")
        ]
        report = format_report(checks)
        assert "impact" in report
        assert "foo breaks bar baz qux" in report
        assert "pip install foo" in report

    def test_missing_recommended_does_not_say_failed(self):
        """Missing recommended deps don't fail the overall report."""
        checks = [DepCheck("a", "a", False, "recommended",
                           "impact a longer than twenty chars sentence",
                           "pip install a")]
        report = format_report(checks)
        assert "PASS" in report

    def test_status_column_uses_OK_or_MISSING(self):
        checks = [
            DepCheck("a", "a", True, "critical", "impact a long enough sentence here please",
                     "pip install a"),
            DepCheck("b", "b", False, "optional", "impact b long enough sentence here please",
                     "pip install b"),
        ]
        report = format_report(checks)
        assert "OK" in report
        assert "MISSING" in report


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

class TestMain:
    def test_returns_zero_when_all_critical_present(self, capsys, monkeypatch):
        fake = [
            DepCheck("a", "a", True, "critical", "impact a long sentence here please thanks",
                     "pip install a"),
            DepCheck("b", "b", False, "optional", "impact b long sentence here please thanks",
                     "pip install b"),
        ]
        monkeypatch.setattr("check_deployment_readiness.check_all", lambda: fake)
        rc = main()
        assert rc == 0
        out = capsys.readouterr().out
        assert "PASS" in out

    def test_returns_one_when_critical_missing(self, capsys, monkeypatch):
        fake = [DepCheck("a", "a", False, "critical",
                         "impact a long sentence here please thanks", "pip install a")]
        monkeypatch.setattr("check_deployment_readiness.check_all", lambda: fake)
        rc = main()
        assert rc == 1
        out = capsys.readouterr().out
        assert "FAILED" in out


# ---------------------------------------------------------------------------
# Real-environment smoke check (no monkeypatching)
# ---------------------------------------------------------------------------

class TestRealEnvironment:
    """Verifies the live test environment has the critical deps.

    This is the single most useful test in this file from a CI perspective —
    if a future PR removes a critical dep from requirements.txt and breaks
    deployments silently, this test fails loudly.
    """

    def test_critical_deps_installed_in_test_env(self):
        checks = check_all()
        missing = critical_missing(checks)
        assert missing == [], (
            f"Critical deps missing in test env: {[c.package for c in missing]}. "
            "This means requirements.txt is incomplete or stale. CI is supposed "
            "to install everything in requirements.txt before running tests."
        )
