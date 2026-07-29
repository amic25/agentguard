# Plugin authoring

Plugins let organizations enforce agent-specific policies without forking AgentGuard. Plugins execute as trusted Python code in the scanner process.

```python
from collections.abc import Iterable

from agentguard.context import SourceFile
from agentguard.models import Finding, Severity
from agentguard.rules import Rule, RuleMetadata


class NoProductionDebugTool(Rule):
    metadata = RuleMetadata(
        id="ACME001",
        title="Production debug tool enabled",
        severity=Severity.HIGH,
        category="acme-policy",
        description="Disallows the internal debug tool in deployable agents.",
    )

    def scan(self, source: SourceFile) -> Iterable[Finding]:
        for line_number, line in enumerate(source.lines, 1):
            if "DebugProductionTool(" in line:
                yield self.finding(
                    source,
                    line_number,
                    "The internal production debug tool is registered.",
                    "The agent could access privileged production diagnostics.",
                    "Remove the tool or restrict it to an isolated development policy.",
                )


rules = [NoProductionDebugTool]
```

Load a local importable module. Plugins execute inside the scanner process, so `plugins` is only honoured in a config the operator vouches for with `--config`; it is rejected in a config discovered inside the repository being scanned. See [Security model](SECURITY_MODEL.md#configuration-trust-boundary).

```yaml
# agentguard scan . --config agentguard-operator.yml
plugins:
  - acme_agentguard_rules
```

For a distributable package, declare an entry point:

```toml
[project.entry-points."agentguard.rules"]
acme = "acme_agentguard_rules:rules"
```

An entry point may expose a `Rule` instance/class, a list or tuple of rules/classes, or a zero-argument factory returning that list. Rule IDs must be globally unique. Namespace third-party IDs to avoid collisions.

Test positive and negative cases, source locations, malformed input, and suppressions. Rules must not execute or import scanned code, access the network unexpectedly, mutate source files, or include sensitive matched text in finding messages.

That last constraint extends to exceptions. When a rule raises, the scanner records the exception text in `ScanResult.errors`, which reaches JSON, Markdown, SARIF `toolExecutionNotifications`, and the terminal — all of which are commonly uploaded as CI artifacts. A rule that quotes matched source in an error message discloses it. Report the location; never the value.
