from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    provider: str = "local"  # "local" | "openai"
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5-coder:7b"
    api_key: str = "ollama"
    temperature: float = 0.2
    max_tokens: int = 4096
    force_tools: bool = True
    max_iterations: int = 3
    default_lang: str = "python"
    sandbox_timeout: int = 10
    code_theme: str = "dracula"


def load_config() -> Config:
    config = Config()
    config_path = Path.home() / ".config" / "scripy" / "config.toml"

    if config_path.exists():
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        model_section = data.get("model", {})
        agent_section = data.get("agent", {})
        theme_section = data.get("theme", {})

        if "provider" in model_section:
            config.provider = model_section["provider"]
        if "base_url" in model_section:
            config.base_url = model_section["base_url"]
        if "model" in model_section:
            config.model = model_section["model"]
        if "api_key" in model_section:
            config.api_key = model_section["api_key"]
        if "temperature" in model_section:
            config.temperature = model_section["temperature"]
        if "max_tokens" in model_section:
            config.max_tokens = model_section["max_tokens"]

        if "force_tools" in agent_section:
            config.force_tools = agent_section["force_tools"]
        if "max_iterations" in agent_section:
            config.max_iterations = agent_section["max_iterations"]
        if "default_lang" in agent_section:
            config.default_lang = agent_section["default_lang"]
        if "sandbox_timeout" in agent_section:
            config.sandbox_timeout = agent_section["sandbox_timeout"]

        if "code_theme" in theme_section:
            config.code_theme = theme_section["code_theme"]

    # Env var overrides api_key when using OpenAI provider
    if config.provider == "openai":
        env_key = os.environ.get("OPENAI_API_KEY")
        if env_key:
            config.api_key = env_key

    return config
