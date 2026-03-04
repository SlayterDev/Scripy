from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5-coder:7b"
    api_key: str = "ollama"
    temperature: float = 0.2
    max_tokens: int = 2048
    max_iterations: int = 3
    default_lang: str = "python"
    sandbox_timeout: int = 10


def load_config() -> Config:
    config = Config()
    config_path = Path.home() / ".config" / "scripy" / "config.toml"

    if config_path.exists():
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

        model_section = data.get("model", {})
        agent_section = data.get("agent", {})

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

        if "max_iterations" in agent_section:
            config.max_iterations = agent_section["max_iterations"]
        if "default_lang" in agent_section:
            config.default_lang = agent_section["default_lang"]
        if "sandbox_timeout" in agent_section:
            config.sandbox_timeout = agent_section["sandbox_timeout"]

    return config
