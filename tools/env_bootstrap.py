"""Normalize environment variables often injected from Secret Manager (strip whitespace)."""

import os

# Cloud Run maps secrets to these env vars; trailing newlines break OpenAI and other clients.
_SECRET_ENV_NAMES = (
    "OPENAI_API_KEY",
    "TAVILY_API_KEY",
    "MCP_DIAGNOSIS_AUTH_TOKEN",
    "AUTH_API_KEY",
    "RAGIE_API_KEY",
)


def strip_secret_env_vars() -> None:
    for name in _SECRET_ENV_NAMES:
        value = os.environ.get(name)
        if value is not None:
            os.environ[name] = value.strip()
