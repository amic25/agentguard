"""Rules for permissions, execution, injection, APIs, and validation."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable

from agentguard.context import SourceFile
from agentguard.models import Finding, Severity
from agentguard.rules.base import Rule, RuleMetadata


def _calls(source: SourceFile) -> Iterable[ast.Call]:
    tree = source.python_tree()
    if tree:
        yield from (node for node in ast.walk(tree) if isinstance(node, ast.Call))


def _name(node: ast.AST) -> str:
    """Dotted name of a call target, or "" when the receiver is not a plain name.

    Returning the bare attribute when the receiver is unresolvable made every
    `something().exec(...)` read as the builtin `exec`. `super().exec(*command)` in a
    sandbox wrapper was reported as critical arbitrary code execution, twice, in
    openai-agents-python. An unresolvable receiver means we do not know what is being
    called, and "do not know" must not resolve to "the most dangerous thing it could be".
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _name(node.value)
        return f"{parent}.{node.attr}" if parent else ""
    return ""


def _is_literal(node: ast.expr) -> bool:
    """True for an expression fixed at author time, with no runtime input."""
    try:
        ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False
    return True


class DangerousExecutionRule(Rule):
    metadata = RuleMetadata(
        "AG002",
        "Unsafe command execution",
        Severity.CRITICAL,
        "system-access",
        "Detects agent-reachable command execution.",
        languages=frozenset({"python", "javascript", "typescript"}),
    )
    _js = re.compile(r"\b(?:exec|execSync|spawn|spawnSync)\s*\(")

    def scan(self, source: SourceFile) -> Iterable[Finding]:
        if source.language == "python":
            dangerous = {"eval", "exec", "os.system", "subprocess.run", "subprocess.call", "subprocess.Popen"}
            for call in _calls(source):
                name = _name(call.func)
                if name not in dangerous:
                    continue
                shell = any(
                    keyword.arg == "shell"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                    for keyword in call.keywords
                )
                # eval("{'retries': 3}") has no attacker-controlled input. Reporting it
                # teaches readers that the rule cannot tell reachable from unreachable,
                # which is how a scanner earns being switched off.
                if call.args and all(_is_literal(argument) for argument in call.args) and not shell:
                    continue
                if shell and call.args and isinstance(call.args[0], ast.List | ast.Tuple):
                    # shell=True with an argument *vector* is a portability bug, not an
                    # injection: POSIX passes only argv[0] to the shell and silently drops
                    # the rest, while Windows joins them. Describing it as an injection
                    # risk sends readers looking for untrusted input that is not there -
                    # measured as a false positive in modelcontextprotocol/python-sdk.
                    yield self.finding(
                        source,
                        call.lineno,
                        f"`{name}` passes an argument list with `shell=True`.",
                        "The two are mutually exclusive: on POSIX the shell receives only the first "
                        "element and every later argument is silently discarded, so the command runs "
                        "differently - or not at all - depending on the platform.",
                        "Drop `shell=True` and keep the argument list, which is also the safer form. "
                        "Only if a shell is genuinely required, pass a single string instead, and then "
                        "treat every interpolated value as untrusted.",
                        column=call.col_offset + 1,
                        confidence="high",
                        metadata={"defect_class": "portability"},
                    )
                elif name in {"eval", "exec", "os.system"} or shell:
                    yield self.finding(
                        source,
                        call.lineno,
                        f"The code invokes `{name}` with no enforceable command boundary.",
                        "Prompt-controlled or tool-controlled values can become arbitrary code or shell commands.",
                        "Replace free-form execution with an allowlisted operation map, fixed arguments, a sandbox, and strict time/resource limits.",
                        column=call.col_offset + 1,
                    )
        elif source.language in {"javascript", "typescript"}:
            for number, line in enumerate(source.lines, 1):
                match = self._js.search(line)
                if match:
                    yield self.finding(
                        source,
                        number,
                        "A child-process execution primitive is exposed in agent code.",
                        "Untrusted model output may cross the code-to-command boundary and execute host commands.",
                        "Use fixed executable/argument allowlists, disable shell mode, validate every argument, and isolate the process.",
                        column=match.start() + 1,
                    )


class BroadToolPermissionRule(Rule):
    metadata = RuleMetadata(
        "AG003",
        "Overly broad tool permissions",
        Severity.HIGH,
        "permissions",
        "Detects tools with unconstrained capabilities.",
        languages=frozenset({"python", "javascript", "typescript"}),
    )
    _pattern = re.compile(
        r"(?i)(allow_dangerous_code\s*=\s*True|allow_delegation\s*=\s*True|function_map\s*=|tools\s*=\s*\[[^\]]*(?:shell|terminal|filesystem|browser)|allowedTools\s*:\s*\[[^\]]*['\"]\*['\"]|dangerouslyAllowBrowser\s*:\s*true)"
    )

    def scan(self, source: SourceFile) -> Iterable[Finding]:
        for number, line in enumerate(source.lines, 1):
            match = self._pattern.search(line)
            if match:
                yield self.finding(
                    source,
                    number,
                    "An agent or MCP client is configured with a broad or explicitly dangerous tool capability.",
                    "A compromised prompt can use every granted capability, increasing blast radius and enabling multi-step attacks.",
                    "Grant the smallest per-agent tool set, require approval for high-impact actions, and scope credentials and resources per tool.",
                    column=match.start() + 1,
                )


class PromptInjectionRule(Rule):
    metadata = RuleMetadata(
        "AG004",
        "Untrusted content enters prompt",
        Severity.HIGH,
        "prompt-injection",
        "Detects direct interpolation of external content into prompts.",
        languages=frozenset({"python", "javascript", "typescript"}),
    )
    _sources = r"(?:request|req|input|user_input|user_message|web_content|document|page|result|tool_output|message\.content)"

    # This was one pattern of the form `PREFIX \s*= .* (?: f['"] .* \{SRC\} | ... )`.
    # Two unbounded `.*` spans nested inside a search meant the engine tried every split
    # of the second for every split of the first, at every start offset: cubic. A 28 KB
    # line took 34 seconds, and the file size cap allows 1 MB. Since a scanner runs on
    # untrusted input, that is a denial-of-service vector, not a tuning problem.
    #
    # Python 3.10 has neither atomic groups nor possessive quantifiers, so the nesting is
    # removed by searching in two steps instead of one. The alternation could only ever
    # match at or after the end of the assignment prefix, so anchoring the second search
    # to the first match's end accepts exactly the same set of lines - see
    # tests/test_redos.py, which asserts that equivalence over a large input corpus.
    _assignment = re.compile(r"(?i)(?:prompt|system_message|instructions?)\s*=")
    _interpolations = (
        re.compile(rf"(?i)f['\"][^\n]*\{{{_sources}\}}"),
        re.compile(rf"(?i)\.format\([^)]*{_sources}"),
        re.compile(rf"(?i)\+\s*{_sources}"),
    )
    # Bounded by a negated class, so linear already; left as one pattern.
    _template_literal = re.compile(rf"(?i)(?:content|prompt)\s*(?::|=)\s*`[^`]*\$\{{{_sources}\}}")

    def _match(self, line: str) -> re.Match[str] | None:
        assignment = self._assignment.search(line)
        if assignment and any(p.search(line, assignment.end()) for p in self._interpolations):
            return assignment
        return self._template_literal.search(line)

    def scan(self, source: SourceFile) -> Iterable[Finding]:
        for number, line in enumerate(source.lines, 1):
            match = self._match(line)
            if match:
                yield self.finding(
                    source,
                    number,
                    "Potentially untrusted data is interpolated directly into an agent prompt or instruction field.",
                    "Embedded instructions can override intended behavior, exfiltrate context, or trigger privileged tools.",
                    "Separate data from instructions, delimit and label untrusted content, enforce an instruction hierarchy, and validate tool calls independently of model text.",
                    column=match.start() + 1,
                    confidence="medium",
                    references=(
                        "https://owasp.org/www-project-top-10-for-large-language-model-applications/",
                    ),
                )


class UnsafeFileAccessRule(Rule):
    metadata = RuleMetadata(
        "AG005",
        "Unrestricted file access",
        Severity.HIGH,
        "system-access",
        "Detects user-controlled paths and broad filesystem roots.",
        # Not manifests. `directory: "/"` in a Dependabot config locates a dependency
        # manifest; it is not filesystem access, and this rule has no business reading
        # CI configuration at all.
        languages=frozenset({"python", "javascript", "typescript"}),
    )
    _path_input = re.compile(
        r"(?i)(?:open|readFile|writeFile|unlink|rmtree)\s*\([^\n]*(?:user|input|request|args|tool_call)"
    )
    # \b matters: without it, `path` matched inside `streamable_http_path`, reporting an
    # HTTP mount point as a broad filesystem root eight times in one real project.
    _broad = re.compile(r"(?i)\b(?:root_dir|workspace|directory|path)\s*[:=]\s*['\"](?:/|~|\.\.)['\"]")

    def scan(self, source: SourceFile) -> Iterable[Finding]:
        for number, line in enumerate(source.lines, 1):
            match = self._path_input.search(line) or self._broad.search(line)
            if match:
                yield self.finding(
                    source,
                    number,
                    "A filesystem operation accepts a dynamic path or grants access to a broad root.",
                    "Path traversal or prompt manipulation may read secrets, overwrite application files, or destroy host data.",
                    "Resolve paths against a dedicated sandbox root, reject escapes and symlinks, allowlist operations, and default to read-only access.",
                    column=match.start() + 1,
                )


class RiskyExternalAPIRule(Rule):
    metadata = RuleMetadata(
        "AG006",
        "Risky external API usage",
        Severity.MEDIUM,
        "external-api",
        "Detects non-TLS, dynamic, or unbounded outbound requests.",
        languages=frozenset({"python", "javascript", "typescript"}),
        require_nodes=frozenset({"call"}),
    )
    _http = re.compile(
        r"(?i)(?:requests\.(?:get|post|put|delete)|fetch|axios\.(?:get|post)|httpx\.(?:get|post))\s*\(\s*['\"]http://"
    )
    _dynamic = re.compile(
        r"(?i)(?:requests\.(?:get|post)|fetch|axios\.(?:get|post))\s*\(\s*(?:url|uri|endpoint|tool_input|user_input)"
    )

    def scan(self, source: SourceFile) -> Iterable[Finding]:
        for number, line in enumerate(source.lines, 1):
            match = self._http.search(line) or self._dynamic.search(line)
            if match:
                reason = "a plaintext HTTP endpoint" if self._http.search(line) else "a caller-controlled URL"
                yield self.finding(
                    source,
                    number,
                    f"Agent code sends a request to {reason}.",
                    "Requests may leak sensitive context or enable SSRF into private services and cloud metadata endpoints.",
                    "Require HTTPS, allowlist hosts and schemes, block private/link-local IP ranges after DNS resolution, set timeouts, and cap response sizes.",
                    column=match.start() + 1,
                )


class MissingValidationRule(Rule):
    metadata = RuleMetadata(
        "AG007",
        "Tool input lacks validation",
        Severity.MEDIUM,
        "validation",
        "Detects agent tools with untyped or unvalidated input.",
        languages=frozenset({"python", "javascript", "typescript"}),
    )
    _py_decorator = re.compile(r"@(?:tool|function_tool|kernel_function)\b")
    # Was `(?:tool|function)\s*\(`, which matched every JavaScript function expression,
    # including IIFEs in vendored analytics snippets. Only a tool registration is a tool.
    _js_tool = re.compile(r"(?i)\btool\s*\(\s*\{?")

    def scan(self, source: SourceFile) -> Iterable[Finding]:
        lines = source.lines
        for index, line in enumerate(lines):
            if self._py_decorator.search(line):
                window = "\n".join(lines[index : index + 5])
                definition = re.search(r"def\s+\w+\s*\(([^)]*)\)", window)
                if definition and definition.group(1) and "Schema" not in window:
                    params = definition.group(1)
                    if ":" not in params or "**kwargs" in params or "*args" in params:
                        yield self.finding(
                            source,
                            index + 1,
                            "A tool function accepts parameters without a complete typed schema.",
                            "The model can supply unexpected types, fields, or oversized values that bypass assumptions in tool code.",
                            "Define a strict Pydantic/JSON schema, reject unknown fields, constrain lengths and enums, and re-check authorization inside the tool.",
                            confidence="medium",
                        )
            elif source.language in {"javascript", "typescript"} and self._js_tool.search(line):
                window = "\n".join(lines[index : index + 12])
                if not re.search(r"\b(?:schema|parameters|z\.object|inputSchema)\b", window):
                    yield self.finding(
                        source,
                        index + 1,
                        "A JavaScript tool definition has no nearby input schema.",
                        "Unvalidated model-generated arguments may reach sensitive application logic.",
                        "Attach a strict JSON Schema or Zod schema and validate again at the trust boundary.",
                        confidence="medium",
                    )


class HumanApprovalRule(Rule):
    metadata = RuleMetadata(
        "AG008",
        "High-impact action lacks approval gate",
        Severity.HIGH,
        "privileges",
        "Detects autonomous high-impact operations.",
        languages=frozenset({"python", "javascript", "typescript"}),
        # Defining `delete_file` is not deleting a file. Requiring a call on the matched
        # line was most of this rule's false positives across four of five real projects.
        require_nodes=frozenset({"call"}),
    )
    _action = re.compile(
        r"(?i)\b(?:send_email|transfer_funds|delete_(?:file|record|account)|deploy|execute_trade|create_user)\s*\("
    )

    def scan(self, source: SourceFile) -> Iterable[Finding]:
        lines = source.lines
        for index, line in enumerate(lines):
            match = self._action.search(line)
            if match:
                context = "\n".join(lines[max(0, index - 8) : index + 2])
                if not re.search(
                    r"(?i)(approve|confirmation|human.?in.?the.?loop|requires_approval)", context
                ):
                    yield self.finding(
                        source,
                        index + 1,
                        "A consequential side effect is executed without a nearby approval or confirmation gate.",
                        "A hallucination or injected instruction can cause irreversible real-world changes.",
                        "Use a preview/approve/execute workflow, bind approval to exact arguments, add idempotency, and retain an audit trail.",
                        column=match.start() + 1,
                        confidence="medium",
                    )
