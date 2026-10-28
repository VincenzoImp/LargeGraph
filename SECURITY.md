# Reporting security issues

For a security-sensitive report, use the repository's private vulnerability
reporting feature when available, or contact the maintainer through their GitHub
profile. Do not include credentials or private graph data in a public issue.

The beta's local viewer binds to `127.0.0.1`, exposes read-only bounded graph
queries and serves only its report. It has no authentication or multi-user
isolation and is intended for a trusted local computer. Do not expose it through
a public reverse proxy without an appropriate authenticated deployment layer.

Treat datasets, cached artifacts, NumPy files and external CluStRE executables as
inputs from sources you trust. Integrity inventories detect changes relative to
recorded baselines; they are not publisher signatures. The report is generated
with embedded JSON escaping and has no external JavaScript dependency or
telemetry. Inspect provenance files before sharing if source paths are private.
