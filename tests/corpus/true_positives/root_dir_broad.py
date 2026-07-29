"""An agent workspace rooted at the filesystem root grants access to everything."""

workspace = "/"


def build_agent(Agent: type) -> object:
    return Agent(root_dir="/")


# Known gap: the dict-literal form below is NOT detected, because the rule requires the
# key to be followed directly by `=` or `:`. Recorded in WORKLOG.md rather than silently
# excluded from the corpus.
AGENT_CONFIG = {"root_dir": "/"}
