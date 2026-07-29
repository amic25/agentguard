"""Built-in AgentGuard rules."""

from agentguard.rules.base import Rule, RuleMetadata
from agentguard.rules.code import (
    BroadToolPermissionRule,
    DangerousExecutionRule,
    HumanApprovalRule,
    MissingValidationRule,
    PromptInjectionRule,
    RiskyExternalAPIRule,
    UnsafeFileAccessRule,
)
from agentguard.rules.dependencies import UnpinnedDependencyRule
from agentguard.rules.secrets import HardcodedSecretRule

BUILTIN_RULES: tuple[type[Rule], ...] = (
    HardcodedSecretRule,
    DangerousExecutionRule,
    BroadToolPermissionRule,
    PromptInjectionRule,
    UnsafeFileAccessRule,
    RiskyExternalAPIRule,
    MissingValidationRule,
    HumanApprovalRule,
    UnpinnedDependencyRule,
)

__all__ = ["BUILTIN_RULES", "Rule", "RuleMetadata"]
