# Roadmap

AgentGuard’s direction is public and issue-driven. Dates are deliberately omitted until maintainers commit capacity.

## Now — reliable static foundation

- Reduce false positives with AST-aware Python checks and syntax-aware JS/TS parsing.
- Add baseline files and changed-lines-only CI enforcement.
- Expand MCP server/client configuration rules.
- Publish signed PyPI artifacts and a release provenance attestation.
- ~~Establish precision/recall benchmark fixtures.~~ Done: `tests/corpus/` and `make bench`, wired into CI.

## Next — deeper agent context

- Cross-file call graph and source-to-tool data flow.
- Framework adapters for LangChain, CrewAI, AutoGen, OpenAI Agents SDK, and MCP.
- Delegate dependency scanning to `pip-audit`/`osv-scanner` and normalize into `Finding`/SARIF, owning no advisory data ([#16](https://github.com/amic25/agentguard/issues/16)).
- Policy packs for regulated and high-impact agent deployments.
- VS Code integration and language-server diagnostics.

## Later — organizational controls

- Organization policy files and centrally managed rule packs.
- Signed plugin catalog and plugin compatibility contracts.
- Risk trends, inventory export, SBOM correlation, and remediation SLAs.
- Extend the corpus to cover AG003 and AG006, which the current corpus flatters relative to real-world measurement.

## Non-goals

AgentGuard will not execute target projects, become an autonomous penetration-testing tool, or claim that a clean static scan proves an agent is safe. Runtime isolation and human review remain separate controls.

Open a discussion for roadmap proposals and include the user problem, threat model, alternatives, and a small acceptance test.
