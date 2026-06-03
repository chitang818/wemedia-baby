"""Shared schemas, sanitizers, and report builders for browser diagnostics."""

from .constants import COLLECTORS, MODES, STAGES
from .report_builder import build_comparison_report, write_report_bundle
from .risk_rules import evaluate_snapshot_risks
from .sanitize import redact_sensitive, sanitize_cookie_list

__all__ = [
    "COLLECTORS",
    "MODES",
    "STAGES",
    "build_comparison_report",
    "write_report_bundle",
    "evaluate_snapshot_risks",
    "redact_sensitive",
    "sanitize_cookie_list",
]

