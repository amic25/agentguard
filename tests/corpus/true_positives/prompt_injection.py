"""Untrusted content interpolated straight into instructions."""


def build_prompt(user_input: str, web_content: str) -> tuple[str, str]:
    prompt = f"Summarize the following: {user_input}"
    system_message = f"Context: {web_content}"
    return prompt, system_message
