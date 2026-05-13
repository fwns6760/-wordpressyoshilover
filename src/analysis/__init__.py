"""src.analysis — INSIGHT-001 data-analysis pipeline namespace.

This package is intentionally isolated from the existing publish
pipeline. Nothing under ``src/`` outside this package should ever
``import src.analysis`` — see doc/active/INSIGHT-001-data-analysis-pipeline.md.

The package may import existing ``src.source_*`` extractors *read-only*
to reuse their HTML parsers, but it must never call WordPress write APIs,
trigger publish flows, or touch Cloud Scheduler / env / secret values.
"""
