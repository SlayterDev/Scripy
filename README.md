# ▸ scripy

Generate small, single-file scripts using locally hosted LLMs. One command, no cloud.

```
scripy -p "rename all my jpegs by date taken"
```

scripy runs an agentic loop — generate, validate, self-correct, write — entirely on your machine via [Ollama](https://ollama.com) or [LM Studio](https://lmstudio.ai).

---

## Install

Requires Python 3.11+ and a running Ollama or LM Studio instance.

```bash
pipx install .
```

Or for development:

```bash
pip install -e .
```

---

## Quick start

```bash
# Generate a Python script
scripy -p "find duplicate files in a directory"

# Specify output file
scripy -p "find duplicate files in a directory" -o dedup.py

# Generate Bash
scripy -p "backup my home directory to /tmp" --lang bash

# Modify an existing script
scripy -p "add a --dry-run flag" --input dedup.py

# Skip all confirmation prompts (for scripting)
scripy -p "..." -y
```

---

## Confirmation gates

scripy prompts before any side-effectful action.

**Before sandboxed execution:**
```
  ? run script to validate? [y/n/e/v/a] ›
```
| Key | Action |
|-----|--------|
| `y` | Run it |
| `n` | Skip — model continues without sandbox feedback |
| `e` | Open in `$EDITOR` before running |
| `v` | Print script to terminal, then re-prompt |
| `a` | Always yes — skip gate for all remaining iterations |

**Before writing to disk:**
```
  ? write to disk as dedup.py? [y/n] ›
```

Use `-y` / `--yes` to bypass all gates non-interactively.

---

## Configuration

Default config works with a local Ollama instance. Override via `~/.config/scripy/config.toml`:

```toml
[model]
base_url = "http://192.168.1.10:11434/v1"  # remote Ollama
model    = "llama3.1:8b"
api_key  = "ollama"                          # use "lm-studio" for LM Studio
temperature = 0.2
max_tokens  = 2048

[agent]
max_iterations   = 3
default_lang     = "python"
sandbox_timeout  = 10
```

CLI flags override config for a single run:

```bash
scripy --model qwen2.5-coder:7b -p "..."
```

---

## Model recommendations

scripy targets models that run on consumer hardware (~4–8GB RAM).

| Model | Size | Tool calling | Code quality | Notes |
|-------|------|-------------|-------------|-------|
| `llama3.1:8b` | ~4.7GB | Native | Good | **Recommended default** |
| `llama3.2:3b` | ~2.0GB | Native | Fair | Best ultra-low-resource option |
| `qwen2.5-coder:7b` | ~4.4GB | Inline only | Excellent | Best code quality; see note below |
| `deepseek-coder:6.7b` | ~4.0GB | Inline only | Excellent | Same trade-off as qwen-coder |

### Tool calling — what this means in practice

scripy uses the OpenAI function-calling API to let the model invoke tools
(`write_file`, `run_script`, `read_file`, `list_directory`). Models fall into
two categories:

**Native tool calling** (`llama3.1`, `llama3.2`) — the model returns structured
`tool_calls` in the API response. The agentic loop runs cleanly; `run_script`
validation and multi-turn self-correction work as intended.

**Inline tool calling** (`qwen2.5-coder`, `deepseek-coder`) — these models
ignore the tool-calling API and instead append a JSON blob to their text
response. scripy detects and handles this automatically, but the behaviour is
less reliable: the self-correction loop may not fire, and you will see:

```
  ~ inline tool call detected — model is not using structured tool calling
```

For best results with qwen-coder or deepseek-coder, use `--force-tools` to
set `tool_choice=required`. Some model/Ollama version combinations respond
to this correctly; others may fail or produce garbled output — test with your
setup.

```bash
scripy --model qwen2.5-coder:7b --force-tools -p "..."
```

If `--force-tools` causes errors, omit it — the inline fallback will handle it.

---

## CLI reference

```
Usage: scripy [OPTIONS]

  scripy — generate scripts with local LLMs.

Options:
  -p, --prompt TEXT   What script to generate.  [required]
  -o, --output TEXT   Output file path.
  --lang TEXT         Language override (python, bash, etc.).
  --model TEXT        Model name override.
  --input TEXT        Existing script to modify.
  --tui               Launch Textual TUI.  [coming soon]
  -y, --yes           Skip all confirmation gates.
  --force-tools       Set tool_choice=required (native tool-calling models only).
  --version           Show version and exit.
  --help              Show this message and exit.
```

---

## Current state

**Phase 1 — skeleton & config** ✓
**Phase 2 — headless agent** ✓

- Generate → syntax validate → sandbox run → self-correct → write loop
- Confirmation gates (run / write) with keyboard shortcuts
- Inline tool call detection and fallback for models that don't use the tool-calling API
- `~/.config/scripy/config.toml` config with CLI overrides

**Phase 3 — TUI** — not yet implemented (`--tui` falls back to headless)

---

## Development

```bash
pip install -e ".[dev]"
pytest
```
