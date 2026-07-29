# Security model

## Assets and trust boundaries

Agent applications commonly hold model/API credentials, user data, retrieved documents, system prompts, tools, and authority to create side effects. AgentGuard focuses on transitions where attacker-influenced text or tool output crosses into instructions, code, files, networks, credentials, or high-impact actions.

## Threats covered

- credentials committed in source or configuration;
- prompt injection through untrusted user, web, document, message, or tool content;
- arbitrary command/code execution exposed to model output;
- broad tool, filesystem, network, and delegation permissions;
- SSRF and plaintext outbound requests;
- weak or missing tool argument schemas;
- irreversible actions without a bound human approval;
- unpinned, unreproducible dependencies.

The security properties AgentGuard encourages are least privilege, explicit trust boundaries, strict validation, data/instruction separation, deny-by-default outbound access, sandboxed system access, approval for consequential actions, auditable side effects, and reproducible dependencies.

## Scanner threat model

The scanned repository is untrusted. AgentGuard reads supported UTF-8 files but does not import, build, install, or execute them. It skips symlinks, caps file size, and caps the line length handed to regex-based rules by default. Those caps are resource bounds against hostile input, not tuning: a pathological line is how a backtracking regex becomes a denial of service. Bounded coverage is always reported (`truncated_lines`, `skipped_files`) so a bounded scan is not mistaken for a complete one. Reporters do not print matched source lines or secret values.

### Configuration trust boundary

Configuration is the one channel through which a scanned repository can influence the scanner, so it is split into two types that cannot be confused for one another:

| | Source | Trust | May set |
|---|---|---|---|
| `RepoConfig` | `.agentguard.yml` discovered in the repository under scan | **Untrusted** | `exclude`, `max_file_size_kb`, `max_line_length`, `follow_symlinks` |
| `Config` | a path the operator passes to `--config` | Trusted | all of the above, plus `plugins`, `disabled_rules`, `severity_overrides` |

`plugins` is not a field on the untrusted type. A repository cannot name a module for the scanner to import, because there is nowhere in `RepoConfig` to put the name — the boundary is held by the shape of the type, not by a check that a later refactor could drop.

The two are combined only by `Config.tightened_by`, which is monotone toward safety: exclusions are append-only, `max_file_size_kb` and `max_line_length` take the minimum, and `follow_symlinks` takes the conjunction. A hostile repository can therefore make its own scan stricter, slower, or narrower — never laxer. Supplying an operator-only key in a discovered config is an error, not a silent ignore, and fails the scan with exit code 2.

Passing `--config` is the operator's explicit act of vouching for a file. Plugin modules named there are trusted code and execute in the AgentGuard process; only enable plugins from trusted packages. Rules registered through `agentguard.rules` entry points are likewise trusted, at the same level as any installed Python package.

## Limitations

Static, local heuristics cannot see runtime IAM policies, dynamic prompt construction, generated code, encrypted secrets, indirect data flow, external MCP server behavior, or controls enforced in infrastructure. JavaScript/TypeScript checks in the first release are lexical rather than full-AST analysis. AgentGuard does not check dependencies against vulnerability advisories at all — use `pip-audit`, `npm audit`, OSV-Scanner, or an SBOM service, which own that data properly.

A clean result is not a certification. Teams should also threat-model agent workflows; sandbox tools; scope credentials; log and review tool calls; test adversarial prompts; scan secrets and dependencies with dedicated tools; and monitor runtime behavior.

## Severity model

| Severity | Meaning |
|---|---|
| Critical | likely direct credential compromise or arbitrary code/command execution |
| High | strong path to high-impact abuse, data access, or broad privilege misuse |
| Medium | exploitable with additional conditions or materially weak trust-boundary control |
| Low | hardening or supply-chain reproducibility gap |

Confidence is separate from severity. A high-severity, medium-confidence finding deserves investigation even when more context is required.
