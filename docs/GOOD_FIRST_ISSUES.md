# Good first issue backlog

These issue specifications are ready to create after launch. Each is intentionally scoped for a first contribution.

## Add `--quiet` for report-only CI use

**Labels:** `good first issue`, `cli`, `help wanted`  
Add a global or scan option that suppresses the “Report written” status line while preserving report files and exit codes. Include CLI tests and README usage. Acceptance: JSON/SARIF files are unchanged and errors still print.

## Detect Google API keys

**Labels:** `good first issue`, `rule`, `security`  
Add a high-confidence Google API key pattern to `AG001`, synthetic positive/negative tests, and placeholder filtering. Never use a real credential. Acceptance: common documentation placeholders do not trigger.

## Add plain-text report format

**Labels:** `good first issue`, `reporting`, `help wanted`  
Create a dependency-free plain reporter for CI logs that disable color. Preserve severity, rule, location, risk, and remediation. Add reporter and CLI tests.

## Document GitLab SARIF artifact upload

**Labels:** `good first issue`, `documentation`  
Add a tested GitLab CI example under `docs/integrations/`. Explain exit thresholds and artifact retention without claiming native features AgentGuard does not provide.
