"""Tests for scripy/config.py — Config defaults and load_config() TOML loading."""

import pytest

from scripy.config import Config, load_config


class TestConfigDefaults:
    def test_base_url(self):
        assert Config().base_url == "http://localhost:11434/v1"

    def test_model(self):
        assert Config().model == "qwen2.5-coder:7b"

    def test_api_key(self):
        assert Config().api_key == "ollama"

    def test_temperature(self):
        assert Config().temperature == 0.2

    def test_max_tokens(self):
        assert Config().max_tokens == 4096

    def test_force_tools_default_on(self):
        assert Config().force_tools is True

    def test_max_iterations(self):
        assert Config().max_iterations == 3

    def test_default_lang(self):
        assert Config().default_lang == "python"

    def test_sandbox_timeout(self):
        assert Config().sandbox_timeout == 10


class TestLoadConfigNoFile:
    def test_returns_defaults_when_no_config_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        cfg = load_config()
        assert cfg.model == "qwen2.5-coder:7b"
        assert cfg.force_tools is True


class TestLoadConfigModelSection:
    def _write_config(self, tmp_path, content: str):
        config_dir = tmp_path / ".config" / "scripy"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(content)

    def test_overrides_model(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        self._write_config(tmp_path, '[model]\nmodel = "deepseek-coder:6.7b"\n')
        cfg = load_config()
        assert cfg.model == "deepseek-coder:6.7b"

    def test_overrides_temperature(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        self._write_config(tmp_path, "[model]\ntemperature = 0.7\n")
        cfg = load_config()
        assert cfg.temperature == 0.7

    def test_overrides_base_url(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        self._write_config(tmp_path, '[model]\nbase_url = "http://localhost:1234/v1"\n')
        cfg = load_config()
        assert cfg.base_url == "http://localhost:1234/v1"

    def test_unset_keys_keep_defaults(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        self._write_config(tmp_path, '[model]\nmodel = "codellama:7b"\n')
        cfg = load_config()
        assert cfg.temperature == 0.2  # default unchanged


class TestLoadConfigAgentSection:
    def _write_config(self, tmp_path, content: str):
        config_dir = tmp_path / ".config" / "scripy"
        config_dir.mkdir(parents=True)
        (config_dir / "config.toml").write_text(content)

    def test_overrides_max_iterations(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        self._write_config(tmp_path, "[agent]\nmax_iterations = 5\n")
        cfg = load_config()
        assert cfg.max_iterations == 5

    def test_overrides_force_tools(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        self._write_config(tmp_path, "[agent]\nforce_tools = false\n")
        cfg = load_config()
        assert cfg.force_tools is False

    def test_overrides_sandbox_timeout(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        self._write_config(tmp_path, "[agent]\nsandbox_timeout = 30\n")
        cfg = load_config()
        assert cfg.sandbox_timeout == 30

    def test_overrides_default_lang(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        self._write_config(tmp_path, '[agent]\ndefault_lang = "bash"\n')
        cfg = load_config()
        assert cfg.default_lang == "bash"
