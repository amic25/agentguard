# Reddit launch draft

**Suggested communities:** r/netsec (follow self-promotion rules), r/Python, r/LocalLLaMA, r/LangChain, r/devops

**Title:** AgentGuard: open-source static security scanning for AI agent projects

I’m releasing AgentGuard, a Python CLI that scans Python and JS/TS agent code for leaked credentials, unsafe command/file access, broad tool permissions, prompt-injection paths, SSRF-style outbound calls, missing tool schemas, absent approval gates, and vulnerable dependencies.

```bash
pipx install agentguard
agentguard scan .
```

Reports work in the terminal or as JSON, Markdown, and GitHub-compatible SARIF. It’s offline-first, does not execute the scanned project, and supports custom rule plugins. The checks are designed around LangChain, CrewAI, AutoGen, OpenAI agent applications, and MCP patterns without locking into one framework release.

The honest limitation: this is defense-in-depth static analysis, not a safety proof, and the first JS/TS checks are lexical. I’m looking for synthetic false-positive/false-negative cases and contributors for deeper AST/data-flow analysis.

Code and threat model: https://github.com/amic25/agentguard
